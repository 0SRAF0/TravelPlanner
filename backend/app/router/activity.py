"""
Activity Router
Provides endpoints for managing and retrieving activities
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime

from app.db.database import get_activities_collection, get_preferences_collection, get_database
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


class VoteRequest(BaseModel):
    trip_id: str = Field(..., description="Trip ID")
    activity_name: str = Field(..., description="Activity name")
    user_id: str = Field(..., description="User's Google ID")
    vote: str = Field(..., description="'up' or 'down'")


@router.post("/vote", response_model=APIResponse)
async def vote_activity(req: VoteRequest):
    """
    Persist a user's vote for an activity and adjust the activity score.
    Body JSON: { trip_id, activity_name, user_id, vote }
    """
    try:
        trip_id = req.trip_id
        activity_name = req.activity_name
        user_id = req.user_id
        vote = req.vote.lower()

        if vote not in ("up", "down"):
            raise HTTPException(status_code=400, detail="vote must be 'up' or 'down'")

        # DB handles
        db = get_database()
        votes_col = db.votes
        preferences_col = get_preferences_collection()
        activities_col = get_activities_collection()

        # Check previous vote (if any)
        prev = await votes_col.find_one({"trip_id": trip_id, "user_id": user_id, "activity_name": activity_name})

        # Compute score delta:
        def vval(v):
            return 1 if v == "up" else -1

        if prev is None:
            delta = 0.1 * vval(vote)
        else:
            if prev.get("vote") == vote:
                delta = 0.0
            else:
                # remove previous effect and add new one -> double change
                delta = 0.1 * (vval(vote) - vval(prev.get("vote")))

        # Upsert the vote record
        now = datetime.utcnow()
        await votes_col.update_one(
            {"trip_id": trip_id, "user_id": user_id, "activity_name": activity_name},
            {"$set": {"vote": vote, "updated_at": now, "created_at": now}},
            upsert=True,
        )

        # Also store on the preferences document for quick per-user access
        await preferences_col.update_one(
            {"trip_id": trip_id, "user_id": user_id},
            {"$set": {f"votes.{activity_name}": vote, "updated_at": now}},
            upsert=True,
        )

        # Adjust activity score if needed
        if delta != 0.0:
            # Try updating by delta
            await activities_col.update_one(
                {"trip_id": trip_id, "name": activity_name},
                {"$inc": {"score": delta}, "$set": {"updated_at": now}},
            )

            # Clamp the score to [0,1]
            activity = await activities_col.find_one({"trip_id": trip_id, "name": activity_name})
            if activity and "score" in activity:
                new_score = float(activity.get("score", 0.0))
                if new_score < 0:
                    new_score = 0.0
                if new_score > 1:
                    new_score = 1.0
                await activities_col.update_one({"_id": activity.get("_id")}, {"$set": {"score": new_score}})
        else:
            activity = await activities_col.find_one({"trip_id": trip_id, "name": activity_name})

        # Prepare response data
        resp_data = {"trip_id": trip_id, "activity_name": activity_name}
        if activity and "score" in activity:
            resp_data["score"] = float(activity.get("score", 0.0))

        return APIResponse(code=0, msg="ok", data=resp_data)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error saving vote: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record vote: {str(e)}")


class UnvoteRequest(BaseModel):
    trip_id: str = Field(..., description="Trip ID")
    activity_name: str = Field(..., description="Activity name")
    user_id: str = Field(..., description="User's Google ID")


@router.delete("/vote", response_model=APIResponse)
async def unvote_activity(req: UnvoteRequest):
    """
    Remove a user's vote for an activity and adjust the activity score accordingly.
    Body JSON: { trip_id, activity_name, user_id }
    """
    try:
        trip_id = req.trip_id
        activity_name = req.activity_name
        user_id = req.user_id

        db = get_database()
        votes_col = db.votes
        preferences_col = get_preferences_collection()
        activities_col = get_activities_collection()

        prev = await votes_col.find_one({"trip_id": trip_id, "user_id": user_id, "activity_name": activity_name})
        if not prev:
            # Nothing to remove
            return APIResponse(code=0, msg="ok", data={"removed": False})

        # Compute delta to remove previous effect
        def vval(v):
            return 1 if v == "up" else -1

        delta = -0.1 * vval(prev.get("vote"))

        # Delete vote record
        await votes_col.delete_one({"_id": prev.get("_id")})

        # Remove from preferences.votes.<activity_name>
        await preferences_col.update_one(
            {"trip_id": trip_id, "user_id": user_id},
            {"$unset": {f"votes.{activity_name}": ""}, "$set": {"updated_at": datetime.utcnow()}},
        )

        # Adjust activity score
        await activities_col.update_one(
            {"trip_id": trip_id, "name": activity_name},
            {"$inc": {"score": delta}, "$set": {"updated_at": datetime.utcnow()}},
        )

        # Clamp
        activity = await activities_col.find_one({"trip_id": trip_id, "name": activity_name})
        if activity and "score" in activity:
            new_score = float(activity.get("score", 0.0))
            if new_score < 0:
                new_score = 0.0
            if new_score > 1:
                new_score = 1.0
            await activities_col.update_one({"_id": activity.get("_id")}, {"$set": {"score": new_score}})

        return APIResponse(code=0, msg="ok", data={"removed": True})

    except Exception as e:
        print(f"Error removing vote: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove vote: {str(e)}")
