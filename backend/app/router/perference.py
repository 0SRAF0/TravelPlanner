from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.preference_agent import PreferenceAgent
from app.db.database import get_database, get_preferences_collection
from app.models.common import APIResponse
from app.models.preference import Preference as PreferenceDoc

router = APIRouter(prefix="/preferences", tags=["Preferences"])

# Keep a single in-memory agent instance (simple, non-persistent)
_agent = PreferenceAgent()
_TRIP_ID = "default"

# Allowed top-level vibe cards and mapping to agent tags (6 canonical vibes)
_VIBE_MAP: dict[str, str] = {
    "adventure": "adventure",
    "food": "food",
    "nightlife": "nightlife",
    "culture": "culture",
    "relax": "relax",
    "nature": "nature",
}


class CreatePreferenceRequest(BaseModel):
    trip_id: str
    user_id: str
    destination: str | None = Field(None, description="Preferred destination")
    budget_level: int | None = Field(
        default=None, ge=1, le=4, description="1=Budget, 2=Moderate, 3=Comfort, 4=Luxury"
    )
    vibes: list[str] = Field(
        default_factory=list,
        description="Up to 6 cards: Adventure, Food, Nightlife, Culture, Relax, Nature",
    )
    deal_breaker: str | None = None
    notes: str | None = None
    available_dates: list[str] = Field(
        default_factory=list, description="Available date ranges in format 'YYYY-MM-DD:YYYY-MM-DD'"
    )


def _scorecard_from_vibes(vibes: list[str]) -> dict[str, float]:
    # Limit to the 6 cards and map to agent tags
    normalized = []
    for v in vibes:
        key = (v or "").strip().lower()
        if key in _VIBE_MAP:
            normalized.append(_VIBE_MAP[key])

    # Weight by order: 0.9, 0.8, 0.7, then floor at 0.5
    def w(i: int) -> float:
        return max(0.5, round(0.9 - 0.1 * i, 1))

    out: dict[str, float] = {}
    for idx, tag in enumerate(normalized[:6]):
        out[tag] = w(idx)
    return out


@router.post("/", status_code=201, response_model=APIResponse)
async def create_preference(body: CreatePreferenceRequest):
    """
    Add or update a user's preference in the database .
    """
    tid = body.trip_id
    uid = body.user_id
    print(f"[preference] Received preference for trip={tid}, user={uid}, vibes={body.vibes}")

    col = get_preferences_collection()

    # Check if preference already exists
    existing_preference = await col.find_one({"trip_id": tid, "user_id": uid})

    current_time = datetime.utcnow()
    is_update = existing_preference is not None

    if existing_preference:
        # Update existing preference using Preference model
        preference_doc = PreferenceDoc(
            trip_id=tid,
            user_id=uid,
            destination=body.destination,
            budget_level=body.budget_level,
            vibes=body.vibes or [],
            deal_breaker=body.deal_breaker,
            notes=body.notes,
            available_dates=body.available_dates or [],
            created_at=existing_preference.get("created_at", current_time),
            updated_at=current_time,
        )

        await col.update_one(
            {"trip_id": tid, "user_id": uid},
            {"$set": preference_doc.model_dump(exclude={"created_at"})},
        )
    else:
        # Create new preference using Preference model
        preference_doc = PreferenceDoc(
            trip_id=tid,
            user_id=uid,
            destination=body.destination,
            budget_level=body.budget_level,
            vibes=body.vibes or [],
            deal_breaker=body.deal_breaker,
            notes=body.notes,
            available_dates=body.available_dates or [],
            created_at=current_time,
            updated_at=current_time,
        )

        await col.insert_one(preference_doc.model_dump())

    # Track that this user has submitted preferences for this trip (both create and update)
    try:
        db = get_database()
        trips_collection = db.trips

        # Try ObjectId first, then fallback to string ID
        try:
            result = await trips_collection.update_one(
                {"_id": ObjectId(tid)},
                {"$addToSet": {"members_with_preferences": uid}},
            )
        except Exception:
            result = await trips_collection.update_one(
                {"trip_id": tid},
                {"$addToSet": {"members_with_preferences": uid}},
            )

        print(
            f"[add_preference] Updated trip member status: matched={result.matched_count}, modified={result.modified_count}"
        )

        # Broadcast preference submission to all connected clients
        if result.modified_count > 0:  # Only broadcast if this was a new submission
            from app.router.chat import broadcast_to_chat
            try:
                await broadcast_to_chat(tid, {
                    "type": "preference_submitted",
                    "trip_id": tid,
                    "user_id": uid,
                })
                print(f"[add_preference] Broadcasted preference_submitted for user {uid}")
            except Exception as e:
                print(f"[add_preference] Failed to broadcast preference update: {e}")
    except Exception as e:
        print(f"[add_preference] Warning: could not update trip member status: {e}")

    message = f"Preference {'updated' if is_update else 'created'} successfully"
    return APIResponse(
        code=0, msg="ok", data={"success": True, "user_id": uid, "trip_id": tid, "message": message}
    )


@router.get("/aggregate", response_model=APIResponse)
async def get_trip_aggregate(trip_id: str | None = Query(None, description="Trip ID")):
    """
    Get aggregated preferences for a trip
    This data is used by the Trip Planning/Itinerary Agent.
    """
    tid = trip_id or _TRIP_ID

    # Get aggregation from agent
    agg = _agent.aggregate(tid)

    if not agg.members:
        raise HTTPException(
            status_code=404, detail=f"No preferences have been submitted for trip_id: {tid}"
        )

    # Format conflicts
    conflicts = [{"field": key, "reason": reason} for key, reason in agg.conflicts]

    return APIResponse(
        code=0,
        msg="ok",
        data={
            "trip_id": agg.trip_id,
            "members": agg.members,
            "member_count": len(agg.members),
            "coverage": agg.coverage,
            "ready_for_options": agg.ready_for_options,
            "soft_preferences": agg.soft_mean,
            "hard_constraints": agg.hard_union,
            "conflicts": conflicts,
        },
    )


@router.get("/user", response_model=APIResponse)
async def get_user_preference(
    user_id: str = Query(..., description="User ID"),
    trip_id: str | None = Query(None, description="Trip ID"),
):
    """
    Get user preference profile
    """
    tid = trip_id or _TRIP_ID

    # Query MongoDB directly
    col = get_preferences_collection()
    pref_doc = await col.find_one({"trip_id": tid, "user_id": user_id})

    if not pref_doc:
        raise HTTPException(
            status_code=404,
            detail=f"No preference profile found for user_id: {user_id} in trip_id: {tid}",
        )

    # Build response from MongoDB document
    budget_level = pref_doc.get("budget_level")
    vibes = pref_doc.get("vibes", [])
    deal_breaker = pref_doc.get("deal_breaker", "")
    notes = pref_doc.get("notes", "")

    # Convert vibes to scorecard
    scorecard = _scorecard_from_vibes(vibes)

    # Build hard constraints
    hard: dict[str, str] = {}
    if budget_level is not None:
        hard["budget_level"] = str(budget_level)
    if deal_breaker:
        deal_breakers = _agent._normalize_deal_breakers(deal_breaker)
        if deal_breakers:
            hard["deal_breakers"] = ", ".join(deal_breakers)

    # Build summary
    summary_parts = []
    if vibes:
        summary_parts.append(f"Vibes: {', '.join(vibes)}")
    if notes:
        summary_parts.append(notes)
    summary = " | ".join(summary_parts) if summary_parts else "No summary"

    # Get updated timestamp
    updated_at = pref_doc.get("updated_at", datetime.utcnow()).timestamp()

    return APIResponse(
        code=0,
        msg="ok",
        data={
            "user_id": user_id,
            "trip_id": tid,
            "hard_constraints": hard,
            "soft_preferences": scorecard,
            "summary": summary,
            "vector_id": _agent._vec_key(tid, user_id),
            "updated_at": updated_at,
        },
    )
