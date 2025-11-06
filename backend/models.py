"""
Database Models for MongoDB Collections
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class User(BaseModel):
    """
    User model for MongoDB storage
    Stores user information from Google OAuth
    """
    google_id: str = Field(..., description="Google user ID (unique identifier)")
    email: str = Field(..., description="User email address")
    name: str = Field(..., description="User full name")
    given_name: Optional[str] = Field(None, description="User first name")
    family_name: Optional[str] = Field(None, description="User last name")
    picture: Optional[str] = Field(None, description="URL to user profile picture")
    email_verified: bool = Field(default=False, description="Whether email is verified")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Account creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    last_login: datetime = Field(default_factory=datetime.utcnow, description="Last login timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "google_id": "123456789",
                "email": "user@example.com",
                "name": "John Doe",
                "given_name": "John",
                "family_name": "Doe",
                "picture": "https://example.com/photo.jpg",
                "email_verified": True,
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
                "last_login": "2024-01-01T00:00:00"
            }
        }


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

