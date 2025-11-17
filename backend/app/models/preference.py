"""
Database Models for MongoDB Collections
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Preference(BaseModel):
    """
    Preference model for MongoDB storage
    Stores user travel preferences
    """

    trip_id: str = Field(..., description="Trip ID for trips")
    user_id: str = Field(..., description="User's Google ID")
    budget_level: int | None = Field(
        default=None,
        ge=1,
        le=4,
        description="Budget level: 1=Budget, 2=Moderate, 3=Comfort, 4=Luxury",
    )
    vibes: list[str] = Field(
        default_factory=list,
        description="Up to 6 cards: Adventure, Food, Nightlife, Culture, Relax, Nature",
    )
    deal_breaker: str | None = Field(None, description="Deal breaker preferences")
    notes: str | None = Field(None, description="Additional notes")
    available_dates: list[str] = Field(
        default_factory=list,
        description="List of available date ranges in format 'YYYY-MM-DD:YYYY-MM-DD' (e.g., ['2024-01-01:2024-01-15', '2024-02-10:2024-02-20'])",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "trip_id": "trip_123",
                "user_id": "123456789",
                "budget_level": 3,
                "vibes": ["Adventure", "Food", "Nature"],
                "deal_breaker": "No early mornings",
                "notes": "Prefer outdoor activities",
                "available_dates": ["2024-06-01:2024-06-15", "2024-07-01:2024-07-31"],
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
            }
        }
