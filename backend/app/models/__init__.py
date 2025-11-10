"""
Models package for database schemas
"""
from app.models.trip import Trip
from app.models.user import User
from app.models.preference import Preference
from app.models.activity import Activity

__all__ = ["Trip", "User", "Preference", "Activity"]

