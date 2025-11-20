"""
Trip model for collaborative travel planning
"""

from datetime import datetime
from pydantic import BaseModel, Field
import secrets
import string


def generate_trip_code() -> str:
    """Generate a unique 6-character trip code (uppercase alphanumeric)"""
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


class PhaseData(BaseModel):
    """Data for a single phase"""
    status: str = Field(default="pending", description="pending, in_progress, completed")
    options: list[dict] = Field(default_factory=list, description="Voting options for this phase")
    users_ready: list[str] = Field(default_factory=list, description="Users who clicked Voted/Approved")
    ai_decision: dict | str | None = Field(default=None, description="AI's decision for this phase")
    decision_rationale: str | None = Field(default=None, description="Why AI made this decision")
    completed_at: datetime | None = Field(default=None, description="When phase completed")


class UserFairness(BaseModel):
    """Fairness tracking for a user"""
    decisions: dict[str, str] = Field(default_factory=dict, description="Phase -> win/compromise")
    total_wins: int = Field(default=0)
    total_compromises: int = Field(default=0)
    compromise_weight: float = Field(default=0.0, description="Weighted sum of compromises")
    fairness_score: float = Field(default=0.5, description="0=compromising a lot, 1=getting their way")


class PhaseTracking(BaseModel):
    """Phase tracking for trip planning workflow"""
    current_phase: str = Field(default="destination_decision", description="Current active phase")
    phases: dict[str, PhaseData] = Field(
        default_factory=lambda: {
            "destination_decision": PhaseData(),
            "date_selection": PhaseData(),
            "activity_voting": PhaseData(),
            "itinerary_approval": PhaseData()
        }
    )
    fairness_history: dict[str, UserFairness] = Field(default_factory=dict, description="User fairness tracking")


class Trip(BaseModel):
    """
    Collaborative trip model for group travel planning
    """

    trip_code: str = Field(
        default_factory=generate_trip_code, description="Unique 6-character trip code for joining"
    )
    trip_name: str = Field(..., description="Trip name set by creator")
    creator_id: str = Field(..., description="User ID of trip creator")

    # Member tracking
    members: list[str] = Field(
        default_factory=list, description="List of user IDs who have joined the trip"
    )
    members_with_preferences: list[str] = Field(
        default_factory=list, description="List of user IDs who have submitted preferences"
    )

    # Trip metadata (aggregated from preferences)
    destination: str | None = Field(None, description="Most common destination from preferences")
    trip_duration_days: int | None = Field(
        None, description="Most common duration from preferences"
    )

    # Status tracking
    status: str = Field(
        default="collecting_preferences",
        description="Trip status: collecting_preferences, planning, finalized",
    )

    # NEW: Phase tracking
    phase_tracking: PhaseTracking = Field(
        default_factory=PhaseTracking,
        description="Tracks current phase and voting progress"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "trip_code": "XY7K9M",
                "trip_name": "Summer Japan Trip",
                "creator_id": "123456789",
                "members": ["123456789", "987654321"],
                "members_with_preferences": ["123456789"],
                "destination": "Tokyo, Japan",
                "trip_duration_days": 7,
                "status": "collecting_preferences",
                "phase_tracking": {
                    "current_phase": "destination_decision",
                    "phases": {},
                    "fairness_history": {}
                }
            }
        }