import boto3
import os
from botocore.exceptions import ClientError
from langchain_core.tools import tool
from typing import Dict, Any, Optional
from app.db.database import get_preferences_collection
from app.models.preference import Preference


@tool
async def get_all_group_preferences(group_id: str) -> Dict[str, Any]:
    """
    Fetch all user preferences for a specific group.

    Args:
        group_id: The ID of the group

    Returns:
        A dictionary containing all preferences for the group
    """
    try:
        col = get_preferences_collection()
        preferences = await col.find({"group_id": group_id}).to_list(length=None)

        # Convert ObjectId to string
        for pref in preferences:
            if "_id" in pref:
                pref["_id"] = str(pref["_id"])

        return {
            "group_id": group_id,
            "preferences": preferences,
            "count": len(preferences)
        }

    except Exception as e:
        return {"_error": f"Database error: {str(e)}"}

