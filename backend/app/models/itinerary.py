"""
Itinerary model for MongoDB persistence
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ItineraryItem(BaseModel):
    """
    Snapshot of a scheduled activity for a specific day.
    Mirrors ItineraryItem from itinerary_agent, with a few extra optional fields.
    """

    activity_id: str = Field(..., description="Reference to catalog activity id/name")
    name: str | None = Field(default=None, description="Human-readable activity name (optional; details come from activities collection)")
    start_time: str = Field(..., description="HH:MM 24-hour")
    end_time: str = Field(..., description="HH:MM 24-hour")
    notes: str | None = Field(default=None, description="Notes/tips/rationale")

    # Optional geodata and metadata (snapshotted for stability)
    lat: float | None = None
    lng: float | None = None
    category: str | None = None
    rough_cost: int | None = None
    duration_min: int | None = None

    # Optional operational fields
    transport: dict | None = Field(default=None, description="{'mode','duration_min','distance_km','cost'}")
    booking: dict | None = Field(default=None, description="{'vendor','reservation_id','price','currency','url'}")
    status: str | None = Field(default="planned", description="planned|booked|completed|cancelled")
    attendees: list[str] | None = Field(default=None, description="User ids attending")


class DayPlan(BaseModel):
    day: int = Field(..., description="1-based day number")
    date: str | None = Field(default=None, description="YYYY-MM-DD if known")
    summary: str | None = Field(default=None, description="Optional human summary for the day")
    daily_budget_estimate: int | None = Field(default=None, description="Approximate daily spend, per person")
    items: list[ItineraryItem] = Field(default_factory=list)


class Accommodation(BaseModel):
    place_id: str | None = Field(default=None, description="Google Place ID if available")
    name: str
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    check_in_date: str | None = None
    check_out_date: str | None = None
    price_total: float | None = None
    currency: str | None = None
    rating: float | None = None
    review_count: int | None = None
    amenities: list[str] | None = None
    url: str | None = None
    photo_url: str | None = None
    rationale: str | None = None
    score: float | None = None
    fits: list[str] | None = None
    preferred: bool | None = None


class Itinerary(BaseModel):
    """
    Full itinerary document persisted per trip/version.
    """

    trip_id: str = Field(..., description="Associated trip id")
    destination: str | None = Field(default=None, description="Destination snapshot")

    # Versioning and status
    version: int = Field(default=1, description="Monotonic version for this trip")
    is_current: bool = Field(default=True, description="Whether this is the active itinerary")
    status: str = Field(default="proposed", description="proposed|approved|archived")

    # Timing
    start_date: str | None = Field(default=None, description="YYYY-MM-DD")
    trip_duration_days: int | None = Field(default=None)
    timezone: str | None = Field(default=None)

    # Plans and accommodations
    days: list[DayPlan] = Field(default_factory=list)
    accommodations: list[Accommodation] | None = Field(default=None)

    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "trip_id": "6911a4b00ef8e4358798cb05",
                "destination": "Tokyo, Japan",
                "version": 1,
                "is_current": True,
                "status": "proposed",
                "start_date": "2025-12-20",
                "trip_duration_days": 4,
                "days": [
                    {
                        "day": 1,
                        "date": "2025-12-20",
                        "items": [
                            {
                                "activity_id": "act_123",
                                "start_time": "10:00",
                                "end_time": "11:00",
                                "lat": 35.6597,
                                "lng": 139.7005
                            }
                        ]
                    }
                ],
            }
        }


