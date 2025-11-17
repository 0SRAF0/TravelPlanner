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
        description="Trip status: collecting_preferences, planning, complete",
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
            }
        }
