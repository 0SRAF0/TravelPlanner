from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from app.agents.preference_agent import PreferenceAgent, SurveyInput
from datetime import datetime
from app.db.database import get_preferences_collection
from app.models.preference import Preference

router = APIRouter(prefix="/preferences", tags=["preferences"])

# Keep a single in-memory agent instance (simple, non-persistent)
_agent = PreferenceAgent()
_GROUP_ID = "default"

# Allowed top-level vibe cards and mapping to agent tags (6 canonical vibes)
_VIBE_MAP: Dict[str, str] = {
    "adventure": "adventure",
    "food": "food",
    "nightlife": "nightlife",
    "culture": "culture",
    "relax": "relax",
    "nature": "nature",
}


# Request model for API (without timestamps)
class PreferenceRequest(BaseModel):
    group_id: Optional[str] = None
    user_id: str
    budget_level: Optional[int] = Field(default=None, ge=1, le=4)
    vibes: List[str] = Field(default_factory=list, description="Up to 6 cards: Adventure, Food, Nightlife, Culture, Relax, Nature")
    deal_breaker: Optional[str] = None
    notes: Optional[str] = None


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


@router.post("/", status_code=201)
async def add_preference(body: PreferenceRequest):
    """
    Add or update a user's preference in the database using Preference model.
    Also ingests into the in-memory preference agent for aggregation.
    """
    gid = body.group_id or _GROUP_ID
    uid = body.user_id

    col = get_preferences_collection()
    
    # Check if preference already exists
    existing_preference = await col.find_one({"group_id": gid, "user_id": uid})
    
    current_time = datetime.utcnow()
    
    if existing_preference:
        # Update existing preference using Preference model
        preference_doc = Preference(
            group_id=gid,
            user_id=uid,
            budget_level=body.budget_level,
            vibes=body.vibes or [],
            deal_breaker=body.deal_breaker,
            notes=body.notes,
            created_at=existing_preference.get("created_at", current_time),
            updated_at=current_time
        )
        
        await col.update_one(
            {"group_id": gid, "user_id": uid},
            {"$set": preference_doc.model_dump(exclude={"created_at"})}
        )
    else:
        # Create new preference using Preference model
        preference_doc = Preference(
            group_id=gid,
            user_id=uid,
            budget_level=body.budget_level,
            vibes=body.vibes or [],
            deal_breaker=body.deal_breaker,
            notes=body.notes,
            created_at=current_time,
            updated_at=current_time
        )
        
        await col.insert_one(preference_doc.model_dump())

    # Ingest into agent for aggregation
    budget_level = body.budget_level if body.budget_level is not None else None
    scorecard = _scorecard_from_vibes(body.vibes or [])
    deal_breakers = _agent._normalize_deal_breakers(body.deal_breaker or "")
    text_bits: List[str] = []
    if body.vibes:
        text_bits.append(" ".join(body.vibes))
    if body.notes:
        text_bits.append(body.notes)
    free_text = " ".join(text_bits)
    hard: Dict[str, str] = {}
    if budget_level is not None:
        hard["budget_level"] = str(budget_level)
    if deal_breakers:
        hard["deal_breakers"] = ", ".join(deal_breakers)
    _agent.ingest_survey(gid, uid, SurveyInput(text=free_text, hard=hard, soft=scorecard))

    return {"success": True, "user_id": uid, "group_id": gid}


@router.post("/submit")
async def submit_preferences(group_id: Optional[str] = None):
    """
    Submit all preferences for a group to the agent for aggregation.
    Gathers all preferences with the same group_id from the database
    and ingests them into the preference agent.
    """
    gid = group_id or _GROUP_ID
    
    # Fetch all preferences for this group from the database
    col = get_preferences_collection()
    preferences = await col.find({"group_id": gid}).to_list(length=None)
    
    if not preferences:
        raise HTTPException(
            status_code=404, 
            detail=f"No preferences found for group_id: {gid}"
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
        
        # Vibes → scorecard
        scorecard = _scorecard_from_vibes(vibes)
        
        # Deal breakers
        deal_breakers = _agent._normalize_deal_breakers(deal_breaker)
        
        # Free text for embedding
        text_bits: List[str] = []
        if vibes:
            text_bits.append(" ".join(vibes))
        if notes:
            text_bits.append(notes)
        free_text = " ".join(text_bits)
        
        # Ingest into agent
        hard: Dict[str, str] = {}
        if budget_level is not None:
            hard["budget_level"] = str(budget_level)
        if deal_breakers:
            hard["deal_breakers"] = ", ".join(deal_breakers)
        
        _agent.ingest_survey(gid, uid, SurveyInput(text=free_text, hard=hard, soft=scorecard))
        ingested_count += 1
    
    return {
        "success": True,
        "group_id": gid,
        "preferences_ingested": ingested_count
    }

