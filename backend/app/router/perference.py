from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Tuple
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


# Request/Response Models
class PreferenceRequest(BaseModel):
    """Request model for adding/updating preferences"""
    group_id: Optional[str] = None
    user_id: str
    budget_level: Optional[int] = Field(default=None, ge=1, le=4, description="1=Budget, 2=Moderate, 3=Comfort, 4=Luxury")
    vibes: List[str] = Field(default_factory=list, description="Up to 6 cards: Adventure, Food, Nightlife, Culture, Relax, Nature")
    deal_breaker: Optional[str] = None
    notes: Optional[str] = None


class PreferenceResponse(BaseModel):
    """Response after adding/updating a preference"""
    success: bool
    user_id: str
    group_id: str
    message: str = "Preference saved successfully"


class SubmitResponse(BaseModel):
    """Response after submitting preferences to agent"""
    success: bool
    group_id: str
    preferences_ingested: int
    message: str = "Preferences submitted to agent successfully"


class GroupAggregateResponse(BaseModel):
    """Aggregated preferences for a group"""
    group_id: str
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
    group_id: str
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
    Add or update a user's preference in the database.
    
    - Stores preference in MongoDB using Preference model
    - Validates budget_level (1-4) and vibes (6 canonical categories)
    - Automatically ingests into preference agent for aggregation
    
    **Budget Levels:**
    - 1: Budget
    - 2: Moderate
    - 3: Comfort
    - 4: Luxury
    
    **Vibes:** Adventure, Food, Nightlife, Culture, Relax, Nature
    """
    gid = body.group_id or _GROUP_ID
    uid = body.user_id

    col = get_preferences_collection()
    
    # Check if preference already exists
    existing_preference = await col.find_one({"group_id": gid, "user_id": uid})
    
    current_time = datetime.utcnow()
    is_update = existing_preference is not None
    
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
    scorecard = _scorecard_from_vibes(body.vibes or [])
    deal_breakers = _agent._normalize_deal_breakers(body.deal_breaker or "")
    
    # Build free text for embedding
    text_bits: List[str] = []
    if body.vibes:
        text_bits.append(" ".join(body.vibes))
    if body.notes:
        text_bits.append(body.notes)
    free_text = " ".join(text_bits)
    
    # Build hard constraints
    hard: Dict[str, str] = {}
    if body.budget_level is not None:
        hard["budget_level"] = str(body.budget_level)
    if deal_breakers:
        hard["deal_breakers"] = ", ".join(deal_breakers)
    
    # Ingest into agent
    _agent.ingest_survey(gid, uid, SurveyInput(text=free_text, hard=hard, soft=scorecard))

    message = f"Preference {'updated' if is_update else 'created'} and ingested into agent"
    return PreferenceResponse(
        success=True,
        user_id=uid,
        group_id=gid,
        message=message
    )


@router.post("/submit", response_model=SubmitResponse)
async def submit_preferences(
    group_id: Optional[str] = Query(None, description="Group ID to submit preferences for")
):
    """
    Submit all preferences for a group to the agent for aggregation.
    
    - Fetches all preferences with the same group_id from MongoDB
    - Ingests them into the preference agent
    - Prepares data for aggregation
    
    This should be called after all group members have added their preferences.
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
        _agent.ingest_survey(gid, uid, SurveyInput(text=free_text, hard=hard, soft=scorecard))
        ingested_count += 1
    
    return SubmitResponse(
        success=True,
        group_id=gid,
        preferences_ingested=ingested_count
    )


@router.get("/aggregate", response_model=GroupAggregateResponse)
async def get_group_aggregate(
    group_id: Optional[str] = Query(None, description="Group ID to get aggregated preferences for")
):
    """
    Get aggregated preferences for a group.
    
    Returns:
    - Averaged vibe weights (soft preferences)
    - Union of all constraints (budget levels, deal breakers)
    - Conflict detection (budget spread, incompatible preferences)
    - Coverage (percentage of members who submitted)
    - Ready status (≥80% coverage and no conflicts)
    
    This data is used by the Trip Planning/Itinerary Agent.
    """
    gid = group_id or _GROUP_ID
    
    # Get aggregation from agent
    agg = _agent.aggregate(gid)
    
    if not agg.members:
        raise HTTPException(
            status_code=404,
            detail=f"No preferences have been submitted for group_id: {gid}"
        )
    
    # Format conflicts
    conflicts = [
        {"field": key, "reason": reason}
        for key, reason in agg.conflicts
    ]
    
    return GroupAggregateResponse(
        group_id=agg.group_id,
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
    group_id: Optional[str] = Query(None, description="Group ID")
):
    """
    Get individual user preference profile.
    
    Returns:
    - User's soft preferences (vibe weights)
    - User's hard constraints (budget level, deal breakers)
    - Embedding summary
    - Vector ID (for semantic search)
    
    Useful for personalizing recommendations within the group aggregate.
    """
    gid = group_id or _GROUP_ID
    
    # Get profile from agent
    profile = _agent.profiles.get((gid, user_id))
    
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"No preference profile found for user_id: {user_id} in group_id: {gid}"
        )
    
    return UserProfileResponse(
        user_id=profile.user_id,
        group_id=profile.group_id,
        hard_constraints=profile.hard,
        soft_preferences=profile.soft,
        summary=profile.summary,
        vector_id=_agent._vec_key(gid, user_id),
        updated_at=profile.updated_at
    )

