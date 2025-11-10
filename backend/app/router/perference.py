from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Tuple, Any
from app.agents.preference_agent import PreferenceAgent, SurveyInput
from datetime import datetime
from app.db.database import get_preferences_collection, get_database, get_activities_collection
from app.models.preference import Preference
from app.models.activity import Activity
from app.agents.destination_research_agent import DestinationResearchAgent
from app.agents.agent_state import AgentState
from bson import ObjectId

router = APIRouter(prefix="/preferences", tags=["preferences"])

# Keep a single in-memory agent instance (simple, non-persistent)
_agent = PreferenceAgent()
_TRIP_ID = "default"

# Allowed top-level vibe cards and mapping to agent tags (6 canonical vibes)
_VIBE_MAP: Dict[str, str] = {
    "adventure": "adventure",
    "food": "food",
    "nightlife": "nightlife",
    "culture": "culture",
    "relax": "relax",
    "nature": "nature",
}


# Request/Response Models
class PreferenceRequest(BaseModel):
    """Request model for adding/updating preferences"""
    trip_id: Optional[str] = None
    user_id: str
    budget_level: Optional[int] = Field(default=None, ge=1, le=4, description="1=Budget, 2=Moderate, 3=Comfort, 4=Luxury")
    vibes: List[str] = Field(default_factory=list, description="Up to 6 cards: Adventure, Food, Nightlife, Culture, Relax, Nature")
    deal_breaker: Optional[str] = None
    notes: Optional[str] = None
    available_dates: List[str] = Field(default_factory=list, description="Available date ranges (ISO format)")


class PreferenceResponse(BaseModel):
    """Response after adding/updating a preference"""
    success: bool
    user_id: str
    trip_id: str
    message: str = "Preference saved successfully"


class SubmitResponse(BaseModel):
    """Response after submitting preferences to agent"""
    success: bool
    trip_id: str
    preferences_ingested: int
    message: str = "Preferences submitted to agent successfully"


class TripAggregateResponse(BaseModel):
    """Aggregated preferences for a trip"""
    trip_id: str
    members: List[str]
    member_count: int
    coverage: float
    ready_for_options: bool
    soft_preferences: Dict[str, float]
    hard_constraints: Dict[str, List[str]]
    conflicts: List[Dict[str, str]]


class UserProfileResponse(BaseModel):
    """Individual user preference profile"""
    user_id: str
    trip_id: str
    hard_constraints: Dict[str, str]
    soft_preferences: Dict[str, float]
    summary: str
    vector_id: str
    updated_at: float


def _scorecard_from_vibes(vibes: List[str]) -> Dict[str, float]:
    # Limit to the 6 cards and map to agent tags
    normalized = []
    for v in vibes:
        key = (v or "").strip().lower()
        if key in _VIBE_MAP:
            normalized.append(_VIBE_MAP[key])

    # Weight by order: 0.9, 0.8, 0.7, then floor at 0.5
    def w(i: int) -> float:
        return max(0.5, round(0.9 - 0.1 * i, 1))

    out: Dict[str, float] = {}
    for idx, tag in enumerate(normalized[:6]):
        out[tag] = w(idx)
    return out


@router.post("/", status_code=201, response_model=PreferenceResponse)
async def add_preference(body: PreferenceRequest):
    """
    Add or update a user's preference in the database .
    No agent ingestion occurs here.
    
    - Stores preference in MongoDB using Preference model
    - Validates budget_level (1-4) and vibes (6 canonical categories)
    
    Call /preferences/submit to ingest all trip preferences and aggregate.
    
    **Budget Levels:** 1=Budget, 2=Moderate, 3=Comfort, 4=Luxury
    **Vibes:** Adventure, Food, Nightlife, Culture, Relax, Nature
    **Available Dates:** ISO ranges (e.g., ["2024-06-01:2024-06-15"])
    """
    tid = body.trip_id or _TRIP_ID
    uid = body.user_id

    col = get_preferences_collection()
    
    # Check if preference already exists
    existing_preference = await col.find_one({"trip_id": tid, "user_id": uid})
    
    current_time = datetime.utcnow()
    is_update = existing_preference is not None
    
    if existing_preference:
        # Update existing preference using Preference model
        preference_doc = Preference(
            trip_id=tid,
            user_id=uid,
            budget_level=body.budget_level,
            vibes=body.vibes or [],
            deal_breaker=body.deal_breaker,
            notes=body.notes,
            available_dates=body.available_dates or [],
            created_at=existing_preference.get("created_at", current_time),
            updated_at=current_time
        )
        
        await col.update_one(
            {"trip_id": tid, "user_id": uid},
            {"$set": preference_doc.model_dump(exclude={"created_at"})}
        )
    else:
        # Create new preference using Preference model
        preference_doc = Preference(
            trip_id=tid,
            user_id=uid,
            budget_level=body.budget_level,
            vibes=body.vibes or [],
            deal_breaker=body.deal_breaker,
            notes=body.notes,
            available_dates=body.available_dates or [],
            created_at=current_time,
            updated_at=current_time
        )
        
        await col.insert_one(preference_doc.model_dump())

    message = f"Preference {'updated' if is_update else 'created'} successfully"
    return PreferenceResponse(
        success=True,
        user_id=uid,
        trip_id=tid,
        message=message
    )


@router.post("/submit", response_model=SubmitResponse)
async def submit_preferences(
    trip_id: Optional[str] = Query(None, description="Trip ID to submit preferences for"),
    destination: Optional[str] = Query(None, description="Destination, e.g., 'Lisbon, Portugal'"),
    radius_km: float = Query(10.0, description="Search radius in km"),
    max_items: int = Query(20, description="Maximum number of activities to return"),
    preferred_categories: Optional[List[str]] = Query(None, description="Preferred categories (repeat param)"),
):
    """
    Submit all preferences for a trip to the agent for aggregation.
    
    - Fetches all preferences with the same trip_id from MongoDB
    - Ingests them into the preference agent
    - Prepares data for aggregation
    
    This should be called after all trip members have added their preferences.
    """
    tid = trip_id or _TRIP_ID
    
    # Fetch all preferences for this trip from the database
    col = get_preferences_collection()
    preferences = await col.find({"trip_id": tid}).to_list(length=None)
    
    if not preferences:
        raise HTTPException(
            status_code=404, 
            detail=f"No preferences found for trip_id: {tid}"
        )
    
    # Ingest each preference into the agent
    ingested_count = 0
    for pref in preferences:
        uid = pref.get("user_id")
        if not uid:
            continue
            
        budget_level = pref.get("budget_level")
        vibes = pref.get("vibes", [])
        deal_breaker = pref.get("deal_breaker", "")
        notes = pref.get("notes", "")
        
        # Vibes → scorecard (weighted)
        scorecard = _scorecard_from_vibes(vibes)
        
        # Deal breakers (normalized and split)
        deal_breakers = _agent._normalize_deal_breakers(deal_breaker)
        
        # Free text for embedding
        text_bits: List[str] = []
        if vibes:
            text_bits.append(" ".join(vibes))
        if notes:
            text_bits.append(notes)
        free_text = " ".join(text_bits)
        
        # Build hard constraints
        hard: Dict[str, str] = {}
        if budget_level is not None:
            hard["budget_level"] = str(budget_level)
        if deal_breakers:
            hard["deal_breakers"] = ", ".join(deal_breakers)
        
        # Ingest into agent
        _agent.ingest_survey(tid, uid, SurveyInput(text=free_text, hard=hard, soft=scorecard))
        ingested_count += 1
    
    # After ingest, aggregate preferences and invoke destination research agent (if destination provided)
    try:
        agg = _agent.aggregate(tid)
        preferences_summary = {
            "trip_id": tid,
            "members": agg.members,
            "aggregated_vibes": agg.soft_mean,
            "budget_levels": agg.hard_union.get("budget_level", []),
            "conflicts": [f"{k}: {r}" for k, r in agg.conflicts],
            "ready_for_planning": agg.ready_for_options,
            "coverage": agg.coverage
        }
        # Build input state for destination research
        hints: Dict[str, Any] = {
            "radius_km": radius_km,
            "max_items": max_items,
            "preferred_categories": preferred_categories or []
        }
        # If destination was not supplied, try to resolve it from the trip document
        if not destination:
            try:
                db = get_database()
                trip_doc = None
                # Prefer ObjectId lookup if possible
                try:
                    trip_doc = await db.trip.find_one({"_id": ObjectId(tid)})
                except Exception:
                    trip_doc = None
                # Fallbacks: search by string id fields
                if trip_doc is None:
                    trip_doc = await db.trip.find_one({"trip_id": tid}) or await db.trip.find_one({"_id": tid})
                if trip_doc:
                    destination = trip_doc.get("destination") or destination
                    if destination:
                        print(f"[submit_preferences] Resolved destination from trip: {destination}")
            except Exception as e:
                print(f"[submit_preferences] Warning: could not resolve destination for trip {tid}: {e}")
        # Only invoke if we have a destination string
        if destination:
            # Log handoff details (PreferenceAgent → DestinationResearchAgent)
            try:
                import json as _json
                print("\n" + "=" * 80)
                print("  PREFERENCE AGENT → DESTINATION RESEARCH (handoff)")
                print("=" * 80)
                print(f"Trip: {tid}")
                print(f"Destination: {destination}")
                print("Preferences Summary:")
                print(_json.dumps(preferences_summary, indent=2, default=str))
                print("Hints:")
                print(_json.dumps(hints, indent=2, default=str))
            except Exception:
                pass
            dr_agent = DestinationResearchAgent()
            input_state: AgentState = {
                "messages": [],
                "trip_id": tid,
                "agent_data": {"preferences_summary": preferences_summary},
                "destination": destination,
                "hints": hints
            }
            output_state = dr_agent.run(dict(input_state))
            agent_data_out = output_state.get("agent_data", {}) or {}
            activities = agent_data_out.get("activity_catalog", []) or []
            insights = agent_data_out.get("insights", []) or []
            warnings = agent_data_out.get("warnings", []) or []
            metrics = agent_data_out.get("metrics", {}) or {}

            print("\n" + "=" * 80)
            print("  DESTINATION RESEARCH OUTPUT")
            print("=" * 80)
            print(f"Destination: {destination}")
            print(f"Activities returned: {len(activities)}")
            if activities:
                import json as _json
                print("\n📋 ALL ACTIVITIES (Full JSON):")
                print(_json.dumps(activities, indent=2, default=str))
                # Persist activities to MongoDB (replace existing for this trip)
                try:
                    col = get_activities_collection()
                    await col.delete_many({"trip_id": tid})
                    docs = []
                    for a in activities:
                        try:
                            doc = Activity(
                                trip_id=str(a.get("trip_id") or tid),
                                name=str(a.get("name", "")),
                                category=str(a.get("category", "Other")),
                                rough_cost=a.get("rough_cost"),
                                duration_min=a.get("duration_min"),
                                lat=a.get("lat"),
                                lng=a.get("lng"),
                                tags=list(a.get("tags") or []),
                                fits=list(a.get("fits") or []),
                                score=float(a.get("score") or 0.0),
                                rationale=str(a.get("rationale") or "")
                            )
                            docs.append(doc.model_dump())
                        except Exception as e:
                            print(f"[submit_preferences] Skipping invalid activity record: {e}")
                    if docs:
                        res = await col.insert_many(docs)
                        print(f"[submit_preferences] Saved {len(res.inserted_ids)} activities for trip={tid}")
                    else:
                        print("[submit_preferences] No valid activities to save")
                except Exception as e:
                    print(f"[submit_preferences] Warning: failed to save activities: {e}")
            print("\n💡 Insights:")
            for s in insights:
                print(f"  - {s}")
            print("\n⚠️  Warnings:")
            if warnings:
                for w in warnings:
                    print(f"  - {w}")
            else:
                print("  None")
            print("\n📊 Metrics:")
            try:
                import json as _json
                print(_json.dumps(metrics, indent=2, default=str))
            except Exception:
                print(metrics)
        else:
            print("[submit_preferences] No destination provided; skipping destination research agent invocation.")
    except Exception as e:
        # Do not fail the submit call if the research step fails; just log it.
        print(f"[submit_preferences] Warning: downstream generation failed: {e}")

    return SubmitResponse(
        success=True,
        trip_id=tid,
        preferences_ingested=ingested_count
    )


@router.get("/aggregate", response_model=TripAggregateResponse)
async def get_trip_aggregate(
    trip_id: Optional[str] = Query(None, description="Trip ID to get aggregated preferences for")
):
    """
    Get aggregated preferences for a trip.
    
    Returns:
    - Averaged vibe weights (soft preferences)
    - Union of all constraints (budget levels, deal breakers)
    - Conflict detection (budget spread, incompatible preferences)
    - Coverage (percentage of members who submitted)
    - Ready status (≥80% coverage and no conflicts)
    
    This data is used by the Trip Planning/Itinerary Agent.
    """
    tid = trip_id or _TRIP_ID
    
    # Get aggregation from agent
    agg = _agent.aggregate(tid)
    
    if not agg.members:
        raise HTTPException(
            status_code=404,
            detail=f"No preferences have been submitted for trip_id: {tid}"
        )
    
    # Format conflicts
    conflicts = [
        {"field": key, "reason": reason}
        for key, reason in agg.conflicts
    ]
    
    return TripAggregateResponse(
        trip_id=agg.trip_id,
        members=agg.members,
        member_count=len(agg.members),
        coverage=agg.coverage,
        ready_for_options=agg.ready_for_options,
        soft_preferences=agg.soft_mean,
        hard_constraints=agg.hard_union,
        conflicts=conflicts
    )


@router.get("/user/{user_id}", response_model=UserProfileResponse)
async def get_user_profile(
    user_id: str,
    trip_id: Optional[str] = Query(None, description="Trip ID")
):
    """
    Get individual user preference profile.
    
    Returns:
    - User's soft preferences (vibe weights)
    - User's hard constraints (budget level, deal breakers)
    - Embedding summary
    - Vector ID (for semantic search)
    
    Useful for personalizing recommendations within the trip aggregate.
    """
    tid = trip_id or _TRIP_ID
    
    # Get profile from agent
    profile = _agent.profiles.get((tid, user_id))
    
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"No preference profile found for user_id: {user_id} in trip_id: {tid}"
        )
    
    return UserProfileResponse(
        user_id=profile.user_id,
        trip_id=profile.trip_id,
        hard_constraints=profile.hard,
        soft_preferences=profile.soft,
        summary=profile.summary,
        vector_id=_agent._vec_key(tid, user_id),
        updated_at=profile.updated_at
    )

