"""
Database Models for MongoDB Collections
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Preference(BaseModel):
    """
    Preference model for MongoDB storage
    Stores user travel preferences
    """
    group_id: Optional[str] = Field(None, description="Group ID for group trips")
    user_id: str = Field(..., description="User's Google ID")
    budget_level: Optional[int] = Field(default=None, ge=1, le=4, description="Budget level: 1=Budget, 2=Moderate, 3=Comfort, 4=Luxury")
    vibes: List[str] = Field(default_factory=list, description="Up to 6 cards: Adventure, Food, Nightlife, Culture, Relax, Nature")
    deal_breaker: Optional[str] = Field(None, description="Deal breaker preferences")
    notes: Optional[str] = Field(None, description="Additional notes")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "group_id": "group_123",
                "user_id": "123456789",
                "budget_level": 3,
                "vibes": ["Adventure", "Food", "Nature"],
                "deal_breaker": "No early mornings",
                "notes": "Prefer outdoor activities",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }
        }

