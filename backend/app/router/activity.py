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


@router.post("/vote", response_model=APIResponse)
async def vote_activity(
    trip_id: str,
    activity_name: str,
    user_id: str,
    vote: str,  # 'up' or 'down'
):
    """
    Record user vote on an activity.
    Votes are stored per activity and update net_score in real-time.
    """
    try:
        col = get_activities_collection()
        
        # Find activity
        activity = await col.find_one({
            "trip_id": trip_id,
            "name": activity_name
        })
        
        if not activity:
            raise HTTPException(status_code=404, detail=f"Activity '{activity_name}' not found")
        
        # Get existing votes dict
        votes = activity.get("votes", {})
        
        # Update vote
        if vote == "up":
            votes[user_id] = "up"
        elif vote == "down":
            votes[user_id] = "down"
        else:
            # Invalid vote, remove if exists (neutral)
            votes.pop(user_id, None)
        
        # Calculate scores
        upvote_count = sum(1 for v in votes.values() if v == "up")
        downvote_count = sum(1 for v in votes.values() if v == "down")
        net_score = upvote_count - downvote_count
        
        # Update activity in database
        from datetime import datetime
        await col.update_one(
            {"trip_id": trip_id, "name": activity_name},
            {
                "$set": {
                    "votes": votes,
                    "upvote_count": upvote_count,
                    "downvote_count": downvote_count,
                    "net_score": net_score,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Broadcast vote update via WebSocket (non-blocking)
        from app.router.chat import broadcast_to_chat
        import asyncio
        asyncio.create_task(broadcast_to_chat(trip_id, {
            "type": "activity_vote_update",
            "activity_name": activity_name,
            "user_id": user_id,
            "vote": vote,
            "upvote_count": upvote_count,
            "downvote_count": downvote_count,
            "net_score": net_score,
            "timestamp": datetime.utcnow().isoformat()
        }))
        
        return APIResponse(
            code=0,
            msg="ok",
            data={
                "activity_name": activity_name,
                "vote": vote,
                "net_score": net_score,
                "upvote_count": upvote_count,
                "downvote_count": downvote_count
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[vote_activity] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record vote: {str(e)}")