"""
Models package for database schemas
"""

from app.models.activity import Activity
from app.models.preference import Preference
from app.models.trip import Trip
from app.models.user import User

__all__ = ["Trip", "User", "Preference", "Activity"]
