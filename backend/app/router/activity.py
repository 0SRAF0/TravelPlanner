"""
Activity Router
Provides endpoints for managing and retrieving activities
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.db.database import get_activities_collection
from app.models.activity import Activity

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("/", response_model=List[Activity])
async def get_activities(
    trip_id: str = Query(..., description="The ID of the trip to fetch activities for (required)"),
    category: Optional[str] = Query(None, description="Filter by category (Food, Nightlife, Adventure, Culture, Relax, Nature, Other)"),
    min_score: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum score threshold (0.0 - 1.0)"),
    limit: Optional[int] = Query(None, ge=1, description="Maximum number of activities to return")
):
    """
    Get activities for a specific trip with optional filters.
    
    - **trip_id**: Required - The ID of the trip to fetch activities for
    - **category**: Optional filter by activity category
    - **min_score**: Optional filter by minimum score (0.0 - 1.0)
    - **limit**: Optional limit on number of results
    
    Returns a list of activities matching the criteria, sorted by score (highest first).
    """
    try:
        col = get_activities_collection()
        
        # Build query filter - trip_id is required
        query_filter = {"trip_id": trip_id}
        
        if category:
            query_filter["category"] = category
            
        if min_score is not None:
            query_filter["score"] = {"$gte": min_score}
        
        # Execute query
        cursor = col.find(query_filter).sort("score", -1)  # Sort by score descending
        
        if limit:
            cursor = cursor.limit(limit)
            
        activities = await cursor.to_list(length=None)
        
        if not activities:
            return []
        
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
        
        return result
        
    except Exception as e:
        print(f"Error fetching activities: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve activities: {str(e)}"
        )

