"""
Database Models for MongoDB Collections
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TripPlan(BaseModel):
    """
    Trip Plan model (for future use)
    Stores user travel plans
    """
    user_id: str = Field(..., description="User's Google ID")
    destination: str = Field(..., description="Travel destination")
    start_date: datetime = Field(..., description="Trip start date")
    end_date: datetime = Field(..., description="Trip end date")
    budget: Optional[float] = Field(None, description="Trip budget")
    notes: Optional[str] = Field(None, description="Trip notes")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123456789",
                "destination": "Tokyo, Japan",
                "start_date": "2024-06-01T00:00:00",
                "end_date": "2024-06-10T00:00:00",
                "budget": 3000.00,
                "notes": "Cherry blossom season"
            }
        }
