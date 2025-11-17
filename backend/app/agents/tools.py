from typing import Any
from langchain_core.tools import tool

from app.db.database import get_preferences_collection


@tool
async def get_all_trip_preferences(trip_id: str) -> Dict[str, Any]:
    """
    Fetch all user preferences for a specific trip.

    Args:
        trip_id: The ID of the trip

    Returns:
        A dictionary containing all preferences for the trip
    """
    try:
        col = get_preferences_collection()
        preferences = await col.find({"trip_id": trip_id}).to_list(length=None)

        # Convert ObjectId to string
        for pref in preferences:
            if "_id" in pref:
                pref["_id"] = str(pref["_id"])

        return {"trip_id": trip_id, "preferences": preferences, "count": len(preferences)}

    except Exception as e:
        return {"_error": f"Database error: {str(e)}"}
