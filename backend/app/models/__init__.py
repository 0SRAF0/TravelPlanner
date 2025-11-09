"""
Models package for database schemas
"""
from app.models.user import User
from app.models.trip_plan import TripPlan
from app.models.preference import Preference

__all__ = ["User", "TripPlan", "Preference"]

