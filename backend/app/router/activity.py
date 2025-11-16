"""
Activity Router
Provides endpoints for managing and retrieving activities
"""

from fastapi import APIRouter, HTTPException, Query

from app.db.database import get_activities_collection
from app.models.activity import Activity
from app.models.common import APIResponse

router = APIRouter(prefix="/activities", tags=["Activities"])


@router.get("/", response_model=APIResponse)
async def get_activities(
    trip_id: str = Query(..., description="Trip ID"),
):
    """
    Get activities for a specific trip with optional filters.
    """
    try:
        col = get_activities_collection()

        # Build query filter - trip_id is required
        query_filter = {"trip_id": trip_id}

        # Execute query
        cursor = col.find(query_filter).sort("score", -1)  # Sort by score descending

        activities = await cursor.to_list(length=None)

        if not activities:
            return APIResponse(code=0, msg="ok", data=[])

        # Convert MongoDB documents to Activity models
        result = []
        for doc in activities:
            # Remove MongoDB's _id field if present
            if "_id" in doc:
                del doc["_id"]

            try:
                activity = Activity(**doc)
                result.append(activity)
            except Exception as e:
                print(f"Warning: Could not parse activity document: {e}")
                continue

        return APIResponse(code=0, msg="ok", data=result)

    except Exception as e:
        print(f"Error fetching activities: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve activities: {str(e)}")
