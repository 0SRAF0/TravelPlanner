"""
Trip Router
Handles trip creation, joining, and coordination
"""

from datetime import datetime
from collections import Counter
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import asyncio

from app.db.database import get_database, get_preferences_collection, get_activities_collection
from app.models.common import APIResponse
from app.models.trip import Trip
from app.models.activity import Activity
from app.agents.preference_agent import PreferenceAgent, SurveyInput
from app.agents.destination_research_agent import DestinationResearchAgent
from app.agents.agent_state import AgentState

router = APIRouter(prefix="/trips", tags=["Trips"])


class VoteRequest(BaseModel):
    """Request to vote on consensus options - user can select multiple"""
    user_id: str
    options: list[str]  # Allow multiple selections
    phase: str  # destination_decision, date_selection, activity_voting, etc.


async def run_orchestrator_background(
    trip_id: str, destination: str, trip_duration_days: int, selected_dates: str, activity_catalog: list[dict] | None = None
):
    """
    Run the orchestrator agent in the background and broadcast updates to chat.
    """
    print(f"[orchestrator_background] Starting for trip_id={trip_id}, destination={destination}, duration={trip_duration_days}")
    from app.agents.orchestrator_agent import run_orchestrator_agent

    db = get_database()
    messages_collection = db.messages

    # Helper function to broadcast agent status with progress tracking
    agent_start_times = {}
    
    async def broadcast_agent_status(
        agent_name: str,
        status: str,
        step: str,
        progress: dict | int | None = None,
    ):
        from app.router.chat import broadcast_to_chat
        
        # Track elapsed time for running agents
        if status == "running" and agent_name not in agent_start_times:
            agent_start_times[agent_name] = datetime.utcnow()
        
        elapsed_seconds = None
        if agent_name in agent_start_times:
            elapsed_seconds = int((datetime.utcnow() - agent_start_times[agent_name]).total_seconds())
        
        if status in ["completed", "error"]:
            agent_start_times.pop(agent_name, None)
        
        # Dev logging with full details
        print(f"[agent_status] {agent_name} | {status} | {step} | elapsed={elapsed_seconds}s | progress={progress}")

        await broadcast_to_chat(
            trip_id,
            {
                "type": "agent_status",
                "agent_name": agent_name,
                "status": status,
                "step": step,
                "timestamp": datetime.utcnow().isoformat(),
                "progress": progress,
                "elapsed_seconds": elapsed_seconds,
            },
        )

    # Send initial status
    await broadcast_agent_status("Orchestrator", "starting", "Initializing trip planning")

    # Send initial message to chat (broadcast_to_chat now handles database save)
    from app.router.chat import broadcast_to_chat

    await broadcast_to_chat(
        trip_id,
        {
            "senderId": "system",
            "senderName": "AI Assistant",
            "content": f"🚀 Starting trip planning...\nDestination: {destination or 'TBD'}\nDuration: {trip_duration_days} days\nDates: {selected_dates or 'Flexible'}",
            "type": "ai",
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    # Derive start_date from selected_dates ("YYYY-MM-DD:YYYY-MM-DD")
    start_date: str | None = None
    try:
        if isinstance(selected_dates, str) and ":" in selected_dates:
            start_date = selected_dates.split(":", 1)[0]
    except Exception:
        # Non-fatal: leave start_date as None
        start_date = None

    # Update status: analyzing preferences
    await broadcast_agent_status("Preference Agent", "running", "Fetching user preferences from database", progress={"current": 0, "total": 3})

    # Fetch trip to check for phase_tracking (consensus phases)
    trips_collection = db.trips
    try:
        trip_doc = await trips_collection.find_one({"_id": ObjectId(trip_id)})
    except:
        trip_doc = await trips_collection.find_one({"trip_code": trip_id.upper()})
    
    phase_tracking = trip_doc.get("phase_tracking") if trip_doc else None
    
    # Run orchestrator
    initial_state = {
        "trip_id": trip_id,
        "goal": f"Plan a {trip_duration_days}-day trip to {destination or 'TBD'}",
        "agent_data": {
            "destination": destination,
            "trip_duration_days": trip_duration_days,
            "start_date": start_date,
            "phase_tracking": phase_tracking,  # Pass phase_tracking so orchestrator can route to consensus
            **({"activity_catalog": activity_catalog} if activity_catalog else {}),
        },
        # Provide start_date at top-level as well so downstream agents can pick it up
        "start_date": start_date,
        "broadcast_callback": broadcast_agent_status,  # Pass broadcast function to agents
    }

    try:
        # Get preference count for progress tracking
        prefs_collection = get_preferences_collection()
        all_prefs = await prefs_collection.find({"trip_id": trip_id}).to_list(length=None)
        pref_count = len(all_prefs)
        
        await broadcast_agent_status("Preference Agent", "running", f"Analyzing {pref_count} user preferences", progress={"current": 1, "total": 3})
        await asyncio.sleep(0.5)
        
        await broadcast_agent_status("Preference Agent", "running", "Computing group preference summary", progress={"current": 2, "total": 3})
        await asyncio.sleep(0.5)
        
        await broadcast_agent_status("Preference Agent", "completed", "Preferences analyzed", progress={"current": 3, "total": 3})

        # Update status: destination research starting
        await broadcast_agent_status(
            "Destination Research Agent", "starting", f"Preparing to research {destination}", progress={"current": 0, "total": 4}
        )

        result = await run_orchestrator_agent(initial_state)
        
        # After orchestrator returns, decide whether we're DONE or PAUSED waiting for users
        agent_data_out = (result or {}).get("agent_data", {}) or {}
        activities = agent_data_out.get("activity_catalog", []) or []
        activity_count = len(activities)
        
        # Only broadcast destination research completion if we got results
        if activities:
            await broadcast_agent_status(
                "Destination Research Agent", "completed", f"Generated {activity_count} activity suggestions", progress={"current": 4, "total": 4}
            )

        # Note: Itinerary Agent will broadcast its own status updates via broadcast_callback

        # Persist activities produced by orchestrator (if any)
        try:
            agent_data_out = (result or {}).get("agent_data", {}) or {}
            activities = agent_data_out.get("activity_catalog", []) or []
            if activities:
                col = get_activities_collection()
                await col.delete_many({"trip_id": trip_id})
                docs = []
                for a in activities:
                    try:
                        doc = Activity(
                            trip_id=str(a.get("trip_id") or trip_id),
                            name=str(a.get("name", "")),
                            category=str(a.get("category", "Other")),
                            rough_cost=a.get("rough_cost"),
                            duration_min=a.get("duration_min"),
                            lat=a.get("lat"),
                            lng=a.get("lng"),
                            tags=list(a.get("tags") or []),
                            fits=list(a.get("fits") or []),
                            score=float(a.get("score") or 0.0),
                            rationale=str(a.get("rationale") or ""),
                        )
                        docs.append(doc.model_dump())
                    except Exception as e:
                        print(f"[orchestrator_background] Skipping invalid activity record: {e}")
                if docs:
                    res = await col.insert_many(docs)
                    activity_count = len(res.inserted_ids)
                    print(f"[orchestrator_background] ✅ Successfully saved {activity_count} activities for trip={trip_id}")
                    print(f"[orchestrator_background] Activity breakdown by category:")
                    from collections import Counter
                    category_counts = Counter([doc.get('category', 'Other') for doc in docs])
                    for cat, count in category_counts.most_common():
                        print(f"  - {cat}: {count}")
        except Exception as e:
            print(f"[orchestrator_background] ⚠️ Warning: failed to save activities after orchestrator: {e}")

        # Inspect current phase to determine pause vs completion
        trips_collection = db.trips
        try:
            trip_after = await trips_collection.find_one({"_id": ObjectId(trip_id)})
        except:
            trip_after = await trips_collection.find_one({"trip_code": trip_id.upper()})
        
        phase_tracking_out = (trip_after or {}).get("phase_tracking", {}) if trip_after else {}
        phases_out = phase_tracking_out.get("phases", {}) if phase_tracking_out else {}
        current_phase_out = phase_tracking_out.get("current_phase")
        
        waiting_phase = None
        waiting_status = None
        if current_phase_out:
            st = (phases_out.get(current_phase_out) or {}).get("status")
            if st in ["active", "voting_in_progress", "pending"]:
                waiting_phase = current_phase_out
                waiting_status = st
        else:
            # Even if no current_phase, activity_voting may still be open
            av_status = (phases_out.get("activity_voting") or {}).get("status")
            if av_status in ["pending", "active", "voting_in_progress"]:
                waiting_phase = "activity_voting"
                waiting_status = av_status
        
        if waiting_phase:
            # Broadcast paused state instead of completed
            # Compute readiness if available
            users_ready = (phases_out.get(waiting_phase) or {}).get("users_ready", [])
            total_members = len((trip_after or {}).get("members", []))
            pretty_phase = {
                "destination_decision": "destination voting",
                "date_selection": "date voting",
                "activity_voting": "activity voting",
                "itinerary_approval": "itinerary approval",
            }.get(waiting_phase, waiting_phase)
            step_msg = f"Waiting for {pretty_phase} ({len(users_ready)}/{total_members} ready)"
            await broadcast_agent_status("Orchestrator", "paused", step_msg)
            
            # Inform chat and set orchestrator status to paused (broadcast_to_chat now handles database save)
            paused_msg = f"⏸️ Paused: {step_msg}\nI'll resume automatically when everyone is done."
            await broadcast_to_chat(
                trip_id,
                {
                    "senderId": "system",
                    "senderName": "AI Assistant",
                    "content": paused_msg,
                    "type": "ai",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            await trips_collection.update_one(
                {"_id": ObjectId(trip_id)},
                {"$set": {"orchestrator_status": "paused", "updated_at": datetime.utcnow()}}
            )
            print(f"[orchestrator_background] Paused for trip {trip_id}: {step_msg}")
        else:
            # Update status: completed
            await broadcast_agent_status("Orchestrator", "completed", f"Trip planning complete! {activity_count} activities ready", progress=100)
            
            # Send completion message (broadcast_to_chat now handles database save)
            success_msg = f"✅ Trip planning complete!\nSteps taken: {result.get('steps', 0)}\nStatus: {result.get('reason', 'Done')}"
            await broadcast_to_chat(
                trip_id,
                {
                    "senderId": "system",
                    "senderName": "AI Assistant",
                    "content": success_msg,
                    "type": "ai",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            
            # Clear orchestrator running flag
            await trips_collection.update_one(
                {"_id": ObjectId(trip_id)},
                {"$set": {"orchestrator_status": "completed", "updated_at": datetime.utcnow()}}
            )
            
            print(f"[orchestrator_background] Completed for trip {trip_id}")

    except Exception as e:
        # Detailed error logging for devs
        import traceback
        error_details = traceback.format_exc()
        print(f"[orchestrator_background] ❌ ERROR for trip {trip_id}")
        print(f"[orchestrator_background] Error type: {type(e).__name__}")
        print(f"[orchestrator_background] Error message: {str(e)}")
        print(f"[orchestrator_background] Full traceback:\n{error_details}")
        
        # User-friendly error message based on error type
        error_type = type(e).__name__
        if "quota" in str(e).lower() or "rate" in str(e).lower():
            user_error = "API quota exceeded. Please wait a moment and try again."
            await broadcast_agent_status("Orchestrator", "error", "API rate limit reached - retrying soon")
        elif "timeout" in str(e).lower():
            user_error = "Request timed out. Please try again."
            await broadcast_agent_status("Orchestrator", "error", "Request timeout - please retry")
        elif "network" in str(e).lower() or "connection" in str(e).lower():
            user_error = "Network error. Please check your connection and try again."
            await broadcast_agent_status("Orchestrator", "error", "Network connectivity issue")
        else:
            user_error = f"Planning failed: {str(e)[:100]}"
            await broadcast_agent_status("Orchestrator", "error", f"Error: {str(e)[:50]}")

        error_msg = f"❌ {user_error}\nPlease try again or contact support if the issue persists."
        # Message will be saved by broadcast_to_chat below
        
        # Clear orchestrator running flag on error
        db = get_database()
        trips_collection = db.trips
        await trips_collection.update_one(
            {"_id": ObjectId(trip_id)},
            {"$set": {"orchestrator_status": "error", "updated_at": datetime.utcnow()}}
        )

        await broadcast_to_chat(
            trip_id,
            {
                "senderId": "system",
                "senderName": "AI Assistant",
                "content": error_msg,
                "type": "ai",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


class CreateTripRequest(BaseModel):
    trip_name: str = Field(..., description="Name for the trip")
    creator_id: str = Field(..., description="User ID of the creator")
    destination: str | None = Field(None, description="Destination for the trip (optional)")


class JoinTripRequest(BaseModel):
    trip_code: str = Field(..., description="6-character trip code")
    user_id: str = Field(..., description="User ID joining the trip")


class AllInTripRequest(BaseModel):
    trip_id: str = Field(..., description="Trip ID")
    radius_km: float = Field(10.0, description="Search radius in km")
    max_items: int = Field(10, description="Maximum activities")
    preferred_categories: list[str] | None = Field(
        None, description="Preferred categories"
    )

@router.get("/", response_model=APIResponse)
async def get_trip(
    trip_id: str | None = Query(None, description="Trip ID"),
):
    """
    Get trip details including member status (who submitted preferences).
    """
    try:
        db = get_database()
        trips_collection = db.trips

        # Try to find by ObjectId first, then by trip_code
        trip_doc = None
        try:
            trip_doc = await trips_collection.find_one({"_id": ObjectId(trip_id)})
        except:
            trip_doc = await trips_collection.find_one({"trip_code": trip_id.upper()})

        if not trip_doc:
            raise HTTPException(status_code=404, detail=f"Trip {trip_id} not found")

        # Convert ObjectId to string
        trip_doc["trip_id"] = str(trip_doc.pop("_id"))

        # Get user details for members
        users_collection = db.users
        member_details = []
        for user_id in trip_doc.get("members", []):
            user = await users_collection.find_one({"google_id": user_id})
            if user:
                member_details.append(
                    {
                        "user_id": user_id,
                        "name": user.get("name", "Unknown"),
                        "picture": user.get("picture"),
                        "has_submitted_preferences": user_id
                        in trip_doc.get("members_with_preferences", []),
                    }
                )

        trip_doc["member_details"] = member_details

        return APIResponse(code=0, msg="ok", data=trip_doc)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[get_trip] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get trip: {str(e)}")

@router.post("/", response_model=APIResponse)
async def create_trip(body: CreateTripRequest):
    """
    Create a new trip and generate a unique trip code.
    Creator is automatically added to members list.
    """
    print(f"[create_trip] Request: name={body.trip_name}, creator={body.creator_id}, dest={body.destination}")
    try:
        db = get_database()
        trips_collection = db.trips

        # Create trip document
        trip = Trip(
            trip_name=body.trip_name,
            creator_id=body.creator_id,
            members=[body.creator_id],  # Creator automatically joins
            members_with_preferences=[],
            status="collecting_preferences",
            destination=body.destination,
        )

        # Ensure trip_code is unique
        max_attempts = 10
        for _ in range(max_attempts):
            existing = await trips_collection.find_one({"trip_code": trip.trip_code})
            if not existing:
                break
            trip.trip_code = Trip.trip_code  # Regenerate

        # Insert into database
        result = await trips_collection.insert_one(trip.model_dump())
        trip_id = str(result.inserted_id)

        print(
            f"[create_trip] Created trip: {trip.trip_name} (code: {trip.trip_code}, id: {trip_id})"
        )

        return APIResponse(
            code=0,
            msg="ok",
            data={
                "trip_id": trip_id,
                "trip_code": trip.trip_code,
                "trip_name": trip.trip_name,
                "destination": trip.destination,
                "creator_id": body.creator_id,
                "members": [body.creator_id],
            },
        )

    except Exception as e:
        print(f"[create_trip] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create trip: {str(e)}")

@router.delete("/", response_model=APIResponse)
async def delete_trip(
    trip_id: str = Query(..., description="Trip ID to delete"),
    user_id: str = Query(..., description="User ID requesting deletion"),
):
    """Delete a trip. Only creator or members can delete."""
    try:
        db = get_database()
        trips_collection = db.trips

        # Validate trip_id format
        if not ObjectId.is_valid(trip_id):
            return APIResponse(code=400, msg="Invalid trip ID format", data=None)

        # Find the trip
        trip = await trips_collection.find_one({"_id": ObjectId(trip_id)})
        if not trip:
            return APIResponse(code=404, msg="Trip not found", data=None)

        # Check if user is a member
        if user_id not in trip.get("members", []):
            return APIResponse(code=403, msg="You are not a member of this trip", data=None)

        # If user is the creator, delete the entire trip
        if user_id == trip.get("creator_id"):
            result = await trips_collection.delete_one({"_id": ObjectId(trip_id)})

            if result.deleted_count > 0:
                # Cascade delete related data
                preferences_collection = get_preferences_collection()
                messages_collection = db.messages
                activities_collection = db.activities

                # Delete all preferences for this trip
                await preferences_collection.delete_many({"trip_id": trip_id})

                # Delete all chat messages for this trip (chatId = trip_id)
                await messages_collection.delete_many({"chatId": trip_id})

                # Delete all activities for this trip
                await activities_collection.delete_many({"trip_id": trip_id})

                print(f"[delete_trip] Creator deleted trip: {trip_id} and all related data")
                return APIResponse(
                    code=0, msg="Trip deleted successfully", data={"trip_id": trip_id}
                )
            else:
                return APIResponse(code=500, msg="Failed to delete trip", data=None)

        # If user is a regular member, just remove them from the trip
        else:
            # Remove user from members list
            result = await trips_collection.update_one(
                {"_id": ObjectId(trip_id)},
                {"$pull": {"members": user_id, "members_with_preferences": user_id}},
            )

            if result.modified_count > 0:
                # Delete user's preferences for this trip
                preferences_collection = get_preferences_collection()
                await preferences_collection.delete_one({"trip_id": trip_id, "user_id": user_id})

                print(f"[delete_trip] User {user_id} left trip: {trip_id}")
                return APIResponse(code=0, msg="You have left the trip", data={"trip_id": trip_id})
            else:
                return APIResponse(code=500, msg="Failed to leave trip", data=None)

    except Exception as e:
        print(f"[delete_trip] Error deleting trip: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/join", response_model=APIResponse)
async def join_trip(body: JoinTripRequest):
    """
    Join an existing trip using the trip code.
    """
    try:
        db = get_database()
        trips_collection = db.trips

        # Find trip by code
        trip_doc = await trips_collection.find_one({"trip_code": body.trip_code.upper()})

        if not trip_doc:
            raise HTTPException(
                status_code=404, detail=f"Trip with code {body.trip_code} not found"
            )

        trip_id = str(trip_doc["_id"])

        # Check if user already a member
        if body.user_id in trip_doc.get("members", []):
            return APIResponse(
                code=0,
                msg="ok",
                data={
                    "trip_id": trip_id,
                    "trip_code": body.trip_code.upper(),
                    "trip_name": trip_doc.get("trip_name"),
                    "message": "User already a member of this trip",
                    "members": trip_doc.get("members", []),
                },
            )

        # Add user to members list
        result = await trips_collection.update_one(
            {"_id": trip_doc["_id"]},
            {"$addToSet": {"members": body.user_id}, "$set": {"updated_at": datetime.utcnow()}},
        )

        # Fetch updated trip
        updated_trip = await trips_collection.find_one({"_id": trip_doc["_id"]})

        print(f"[join_trip] User {body.user_id} joined trip {body.trip_code}")

        # Broadcast member update to all connected clients
        from app.router.chat import broadcast_to_chat
        try:
            await broadcast_to_chat(trip_id, {
                "type": "member_joined",
                "trip_id": trip_id,
                "user_id": body.user_id,
                "member_count": len(updated_trip.get("members", [])),
            })
        except Exception as e:
            print(f"[join_trip] Failed to broadcast member update: {e}")

        return APIResponse(
            code=0,
            msg="ok",
            data={
                "trip_id": trip_id,
                "trip_code": body.trip_code.upper(),
                "trip_name": updated_trip.get("trip_name"),
                "message": "Successfully joined trip",
                "members": updated_trip.get("members", []),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[join_trip] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to join trip: {str(e)}")


@router.post("/all-in", response_model=APIResponse)
async def trigger_all_in(body: AllInTripRequest):
    """
    Trigger the 'All In' workflow - aggregates preferences and starts orchestrator in background.
    Returns immediately so users can navigate to chat.
    """
    print(f"[all_in] Triggering for trip_id={body.trip_id}")
    import asyncio

    try:
        db = get_database()
        trips_collection = db.trips

        # Get trip document
        try:
            trip_doc = await trips_collection.find_one({"_id": ObjectId(body.trip_id)})
        except:
            trip_doc = await trips_collection.find_one({"trip_code": body.trip_id.upper()})

        if not trip_doc:
            raise HTTPException(status_code=404, detail=f"Trip {body.trip_id} not found")
        
        # Check if orchestrator already started previously
        orchestrator_status = trip_doc.get("orchestrator_status")
        trip_status = trip_doc.get("status")
        if orchestrator_status in ["running", "paused", "completed"] or trip_status in ["planning", "consensus"]:
            print(f"[all_in] Orchestrator already started for trip {body.trip_id} (orchestrator_status={orchestrator_status}, trip_status={trip_status}). Skipping duplicate trigger.")
            trip_id_str = str(trip_doc["_id"])
            return APIResponse(
                code=0,
                msg="ok",
                data={
                    "trip_id": trip_id_str,
                    "status": "already_started",
                    "message": "Planning already started.",
                },
            )
        
        # Mark orchestrator as running
        await trips_collection.update_one(
            {"_id": trip_doc["_id"]},
            {"$set": {"orchestrator_status": "running", "updated_at": datetime.utcnow()}}
        )

        trip_id_str = str(trip_doc["_id"])
        members = trip_doc.get("members", [])
        members_with_prefs = trip_doc.get("members_with_preferences", [])

        # Warning if not all members submitted
        warnings = []
        if len(members_with_prefs) < len(members):
            missing = set(members) - set(members_with_prefs)
            warnings.append(
                f"Not all members have submitted preferences. Missing: {len(missing)} member(s)"
            )

        if not members_with_prefs:
            raise HTTPException(
                status_code=400,
                detail="No preferences submitted yet. At least one member must submit preferences.",
            )

        # Aggregate preferences
        prefs_collection = get_preferences_collection()
        all_prefs = await prefs_collection.find({"trip_id": trip_id_str}).to_list(length=None)
        print(f"[all_in] Found {len(all_prefs)} preferences for trip {trip_id_str}")

        # Find overlapping dates and calculate duration
        # For now, we'll find the most common date range or use the first available
        all_date_ranges = []
        for p in all_prefs:
            if p.get("available_dates"):
                all_date_ranges.extend(p.get("available_dates", []))

        # Pick the most common date range (or first one if no consensus)
        selected_dates = None
        trip_duration_days = None
        if all_date_ranges:
            # Count occurrences of each date range
            date_counter = Counter(all_date_ranges)
            most_common_range = (
                date_counter.most_common(1)[0][0] if date_counter else all_date_ranges[0]
            )

            # Parse the date range (format: "YYYY-MM-DD:YYYY-MM-DD")
            if ":" in most_common_range:
                start_str, end_str = most_common_range.split(":")
                try:
                    from datetime import datetime as dt

                    start_date = dt.fromisoformat(start_str)
                    end_date = dt.fromisoformat(end_str)
                    trip_duration_days = (end_date - start_date).days + 1
                    selected_dates = most_common_range
                except Exception as e:
                    print(f"[all_in] Error parsing dates: {e}")
                    trip_duration_days = 7  # Default fallback
        else:
            trip_duration_days = 7  # Default if no dates provided

        # Aggregate destination from preferences (take the most common one)
        all_destinations = []
        for p in all_prefs:
            if p.get("destination"):
                all_destinations.append(p.get("destination").strip().lower())  # Normalize to lowercase
        
        print(f"[all_in] All destinations from preferences: {all_destinations}")
        
        destination = None
        has_destination_conflict = False
        tied_destinations = []
        if all_destinations:
            dest_counter = Counter(all_destinations)
            most_common = dest_counter.most_common()
            
            print(f"[all_in] Destination vote counts: {dict(dest_counter)}")
            print(f"[all_in] Most common destinations: {most_common}")
            
            # If there's a clear winner (more votes than others), use it
            if len(most_common) == 1 or most_common[0][1] > most_common[1][1]:
                destination = most_common[0][0]
                print(f"[all_in] ✅ Selected destination: {destination} ({most_common[0][1]} votes)")
            else:
                # Tie - let consensus_agent handle it
                tied_destinations = [d for d, count in most_common if count == most_common[0][1]]
                print(f"[all_in] ⚠️ Destination conflict detected: {tied_destinations}")
                print(f"[all_in] Will let consensus_agent resolve in destination_decision phase")
                has_destination_conflict = True
                # Store conflict info for consensus_agent
                destination = None  # Don't pick one arbitrarily
        
        # Fallback to trip's destination if no preferences have it
        if not destination and not has_destination_conflict:
            destination = trip_doc.get("destination")

        # Find overlapping dates across all users
        has_date_conflict = False
        overlapping_date_ranges = []
        no_compatible_dates = False
        
        if all_date_ranges and len(all_date_ranges) > 1:
            from datetime import datetime as dt
            
            try:
                # Parse all date ranges
                parsed_ranges = []
                for date_range in all_date_ranges:
                    if ":" in date_range:
                        start_str, end_str = date_range.split(":")
                        start = dt.fromisoformat(start_str)
                        end = dt.fromisoformat(end_str)
                        parsed_ranges.append((start, end, date_range))
                
                print(f"[all_in] Checking {len(parsed_ranges)} date ranges for overlaps")
                
                # Find all overlapping ranges
                overlaps = set()
                for i in range(len(parsed_ranges)):
                    for j in range(i + 1, len(parsed_ranges)):
                        start1, end1, range1 = parsed_ranges[i]
                        start2, end2, range2 = parsed_ranges[j]
                        
                        # Check if ranges overlap
                        if start1 <= end2 and start2 <= end1:
                            # Calculate the overlapping period
                            overlap_start = max(start1, start2)
                            overlap_end = min(end1, end2)
                            overlap_range = f"{overlap_start.date().isoformat()}:{overlap_end.date().isoformat()}"
                            overlaps.add(overlap_range)
                            print(f"[all_in] Found overlap: {overlap_range} between {range1} and {range2}")
                
                overlapping_date_ranges = list(overlaps)
                
                if len(overlapping_date_ranges) == 0:
                    # No overlaps at all
                    print(f"[all_in] ⚠️ No overlapping dates found! Users need to adjust availability.")
                    no_compatible_dates = True
                elif len(overlapping_date_ranges) == 1:
                    # Single overlap - use it automatically
                    selected_dates = overlapping_date_ranges[0]
                    print(f"[all_in] ✅ Single overlapping period found: {selected_dates}")
                    # Parse to get duration
                    if ":" in selected_dates:
                        start_str, end_str = selected_dates.split(":")
                        start_date = dt.fromisoformat(start_str)
                        end_date = dt.fromisoformat(end_str)
                        trip_duration_days = (end_date - start_date).days + 1
                else:
                    # Multiple overlapping periods - need voting
                    print(f"[all_in] ⚠️ Multiple overlapping periods found: {overlapping_date_ranges}")
                    has_date_conflict = True
                    
            except Exception as e:
                print(f"[all_in] Error checking date overlaps: {e}")
                # If parsing fails, just pick most common
                date_counter = Counter(all_date_ranges)
                most_common_range = date_counter.most_common(1)[0][0] if date_counter else all_date_ranges[0]
                selected_dates = most_common_range

        # Handle no compatible dates case
        if no_compatible_dates:
            print(f"[all_in] ❌ No compatible dates found - notifying users")
            
            # Send message to chat
            from app.router.chat import broadcast_to_chat
            await broadcast_to_chat(trip_id_str, {
                "senderId": "system",
                "senderName": "AI Assistant",
                "content": "⚠️ **No Compatible Dates Found!**\n\nYour available dates don't overlap. Please go back to the preferences page and add more date availability, then click 'All In' again.",
                "type": "ai",
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return APIResponse(
                code=0,
                msg="ok",
                data={
                    "trip_id": trip_id_str,
                    "status": "dates_incompatible",
                    "message": "No overlapping dates found. Please adjust preferences.",
                    "requires_date_update": True
                }
            )
        
        # If there are ANY conflicts (destination or dates), initialize phase_tracking
        if has_destination_conflict or has_date_conflict:
            print(f"[all_in] Conflicts detected - orchestrator will coordinate consensus")
            print(f"  - Destination conflict: {has_destination_conflict}")
            print(f"  - Date conflict: {has_date_conflict}")
            
            # Determine which phase to start with (destination first, then dates)
            if has_destination_conflict:
                current_phase = "destination_decision"
            elif has_date_conflict:
                current_phase = "date_selection"
            else:
                current_phase = None
            
            # Initialize phase tracking for consensus
            phase_tracking = {
                "current_phase": current_phase,
                "phases": {
                    "destination_decision": {
                        "status": "active" if has_destination_conflict else "completed",
                        "started_at": datetime.utcnow() if has_destination_conflict else None,
                        "users_ready": [],
                        "destination_options": tied_destinations if has_destination_conflict else []
                    },
                    "date_selection": {
                        "status": "pending" if has_destination_conflict else ("active" if has_date_conflict else "completed"),
                        "started_at": None if has_destination_conflict else (datetime.utcnow() if has_date_conflict else None),
                        "date_options": overlapping_date_ranges if has_date_conflict else []
                    },
                    "activity_voting": {"status": "pending"},
                    "itinerary_approval": {"status": "pending"}
                }
            }
            
            # Update trip - orchestrator will pass phase_tracking through agent_data
            await trips_collection.update_one(
                {"_id": trip_doc["_id"]},
                {
                    "$set": {
                        "trip_duration_days": trip_duration_days,
                        "selected_dates": selected_dates,
                        "status": "consensus",
                        "phase_tracking": phase_tracking,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
            
            # Broadcast to chat and navigate
            from app.router.chat import broadcast_to_chat
            conflict_msg = []
            if has_destination_conflict:
                conflict_msg.append("destination")
            if has_date_conflict:
                conflict_msg.append("dates")
            
            message = f"Conflicts detected in {' and '.join(conflict_msg)}. Time to vote!"
            
            await broadcast_to_chat(trip_id_str, {
                "type": "navigate_to_chat",
                "trip_id": trip_id_str,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Start orchestrator - it will see phase_tracking and route to consensus_agent first
            asyncio.create_task(
                run_orchestrator_background(
                    trip_id_str, None, trip_duration_days, selected_dates  # destination=None, consensus will resolve it
                )
            )
            
            return APIResponse(
                code=0,
                msg="ok",
                data={
                    "trip_id": trip_id_str,
                    "status": "consensus",
                    "message": "Orchestrator started with consensus phase.",
                    "requires_consensus": True
                },
            )

        # No conflict - proceed with normal flow
        # ALWAYS initialize phase_tracking for activity voting (even without conflicts)
        phase_tracking = {
            "current_phase": None,  # Will be set to activity_voting after destination research
            "phases": {
                "destination_decision": {
                    "status": "completed",
                    "started_at": None,
                    "users_ready": [],
                    "destination_options": []
                },
                "date_selection": {
                    "status": "completed",
                    "started_at": None,
                    "date_options": []
                },
                "activity_voting": {
                    "status": "pending",  # Will be set to active after activities generated
                    "users_ready": []
                },
                "itinerary_approval": {
                    "status": "pending",
                    "users_ready": []
                }
            }
        }
        
        # Update trip with aggregated values and phase tracking
        await trips_collection.update_one(
            {"_id": trip_doc["_id"]},
            {
                "$set": {
                    "destination": destination,
                    "trip_duration_days": trip_duration_days,
                    "selected_dates": selected_dates,
                    "status": "planning",
                    "phase_tracking": phase_tracking,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        print(f"[all_in] Starting orchestrator for trip {trip_id_str}")
        print(f"[all_in]   Destination: {destination}")
        print(f"[all_in]   Duration: {trip_duration_days} days")
        print(f"[all_in]   Selected dates: {selected_dates}")
        print(f"[all_in]   Members: {len(members_with_prefs)}/{len(members)} submitted preferences")

        # Preference ingestion and aggregation, plus optional destination research
        '''
        Orchestrator does this already so commenting it out. 
        try:
            agent = PreferenceAgent()
            ingested_count = 0
            for pref in all_prefs:
                uid = pref.get("user_id")
                if not uid:
                    continue

                budget_level = pref.get("budget_level")
                vibes = pref.get("vibes", [])
                deal_breaker = pref.get("deal_breaker", "")
                notes = pref.get("notes", "")

                # Build scorecard weighted by order
                def _w(i: int) -> float:
                    return max(0.5, round(0.9 - 0.1 * i, 1))

                normalized_vibes = [str(v).strip().lower() for v in vibes]
                scorecard = {tag: _w(i) for i, tag in enumerate(normalized_vibes[:6])}

                # Deal breakers normalized via agent helper
                deal_breakers = agent._normalize_deal_breakers(deal_breaker)

                # Free text and hard constraints
                text_bits: list[str] = []
                if vibes:
                    text_bits.append(" ".join(vibes))
                if notes:
                    text_bits.append(notes)
                free_text = " ".join(text_bits)

                hard: dict[str, str] = {}
                if budget_level is not None:
                    hard["budget_level"] = str(budget_level)
                if deal_breakers:
                    hard["deal_breakers"] = ", ".join(deal_breakers)

                agent.ingest_survey(
                    trip_id_str,
                    uid,
                    SurveyInput(text=free_text, hard=hard, soft=scorecard),
                )
                ingested_count += 1

            agg = agent.aggregate(trip_id_str)
            preferences_summary = {
                "trip_id": trip_id_str,
                "members": agg.members,
                "aggregated_vibes": agg.soft_mean,
                "budget_levels": agg.hard_union.get("budget_level", []),
                "conflicts": [f"{k}: {r}" for k, r in agg.conflicts],
                "ready_for_planning": agg.ready_for_options,
                "coverage": agg.coverage,
            }

            hints = {
                "radius_km": body.radius_km,
                "max_items": body.max_items,
                "preferred_categories": body.preferred_categories or [],
            }

            if destination:
                try:
                    import json as _json

                    print("\n" + "=" * 80)
                    print("PREFERENCE AGENT → DESTINATION RESEARCH (handoff)")
                    print("=" * 80)
                    print(f"Trip: {trip_id_str}")
                    print(f"Destination: {destination}")
                    print("Preferences Summary:")
                    print(_json.dumps(preferences_summary, indent=2, default=str))
                    print("Hints:")
                    print(_json.dumps(hints, indent=2, default=str))
                except Exception:
                    pass

                dr_agent = DestinationResearchAgent()
                input_state: AgentState = {
                    "messages": [],
                    "trip_id": trip_id_str,
                    "agent_data": {
                        "preferences_summary": preferences_summary,
                        "destination": destination,
                        "hints": hints,
                    },
                }
                output_state = dr_agent.run(dict(input_state))
                agent_data_out = output_state.get("agent_data", {}) or {}
                activities = agent_data_out.get("activity_catalog", []) or []
                insights = agent_data_out.get("insights", []) or []
                warnings_ext = agent_data_out.get("warnings", []) or []
                metrics = agent_data_out.get("metrics", {}) or {}

                print("\n" + "=" * 80)
                print("  DESTINATION RESEARCH OUTPUT")
                print("=" * 80)
                print(f"Destination: {destination}")
                print(f"Activities returned: {len(activities)}")

                if activities:
                    try:
                        col = get_activities_collection()
                        await col.delete_many({"trip_id": trip_id_str})
                        docs = []
                        for a in activities:
                            try:
                                doc = Activity(
                                    trip_id=str(a.get("trip_id") or trip_id_str),
                                    name=str(a.get("name", "")),
                                    category=str(a.get("category", "Other")),
                                    rough_cost=a.get("rough_cost"),
                                    duration_min=a.get("duration_min"),
                                    lat=a.get("lat"),
                                    lng=a.get("lng"),
                                    tags=list(a.get("tags") or []),
                                    fits=list(a.get("fits") or []),
                                    score=float(a.get("score") or 0.0),
                                    rationale=str(a.get("rationale") or ""),
                                )
                                docs.append(doc.model_dump())
                            except Exception as e:
                                print(f"[all_in] Skipping invalid activity record: {e}")
                        if docs:
                            res = await col.insert_many(docs)
                            print(f"[all_in] Saved {len(res.inserted_ids)} activities for trip={trip_id_str}")
                        else:
                            print("[all_in] No valid activities to save")
                    except Exception as e:
                        print(f"[all_in] Warning: failed to save activities: {e}")

                print("\n💡 Insights:")
                for s in insights:
                    print(f"  - {s}")
                print("\n⚠️  Warnings:")
                if warnings_ext:
                    for w in warnings_ext:
                        print(f"  - {w}")
                else:
                    print("  None")
                print("\n📊 Metrics:")
                try:
                    import json as _json
                    print(_json.dumps(metrics, indent=2, default=str))
                except Exception:
                    print(metrics)
            else:
                print(
                    "[all_in] No destination set on trip; skipping destination research agent invocation."
                )
        except Exception as e:
            # Do not fail the all-in call if the research step fails; just log it.
            print(f"[all_in] Warning: preference aggregation or research failed: {e}")
            '''

        # Broadcast to all users to navigate to chat BEFORE returning response
        # This ensures other users receive the navigation message before the initiating user navigates
        from app.router.chat import broadcast_to_chat
        await broadcast_to_chat(trip_id_str, {
            "type": "navigate_to_chat",
            "trip_id": trip_id_str,
            "message": "Let's Go! Planning has started.",
            "timestamp": datetime.utcnow().isoformat()
        })
        print(f"[all_in] Broadcasted navigate_to_chat to all users in trip {trip_id_str}")

        # Start orchestrator in background
        asyncio.create_task(
            run_orchestrator_background(
                trip_id_str, destination, trip_duration_days, selected_dates
            )
        )

        # Return immediately so frontend can navigate to chat
        return APIResponse(
            code=0,
            msg="ok",
            data={
                "trip_id": trip_id_str,
                "destination": destination,
                "trip_duration_days": trip_duration_days,
                "selected_dates": selected_dates,
                "warnings": warnings,
                "message": "Orchestrator started. Check chat for real-time updates.",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        # Log full exception to server console for debugging
        import traceback

        print(f"[all_in] Error: {e}")
        traceback.print_exc()
        # Return a controlled APIResponse with error details (safe for dev)
        return APIResponse(
            code=1,
            msg="error",
            data={
                "error": "Failed to trigger all-in",
                "details": str(e),
            },
        )


@router.get("/user", response_model=APIResponse)
async def get_user_trips(
    user_id: str = Query(..., description="User ID"),
):
    """Get all trips for a specific user"""
    try:
        db = get_database()
        trips_collection = db.trips

        # Find trips where user is a member
        trips = await trips_collection.find({"members": user_id}).to_list(length=None)

        # Convert ObjectIds
        for trip in trips:
            trip["trip_id"] = str(trip.pop("_id"))

        return APIResponse(code=0, msg="ok", data=trips)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

class MarkReadyRequest(BaseModel):
    user_id: str
    phase: str

@router.post("/{trip_id}/phases/mark-ready", response_model=APIResponse)
async def mark_user_ready(
    trip_id: str,
    request: MarkReadyRequest,
):
    """
    Mark a user as ready to proceed from current phase.
    This is triggered when user clicks "Voted" or "Approved" button.
    When all users ready, triggers Consensus Agent.
    """
    user_id = request.user_id
    phase = request.phase
    try:
        db = get_database()
        trips_collection = db.trips
        
        # Find trip
        try:
            trip_doc = await trips_collection.find_one({"_id": ObjectId(trip_id)})
        except:
            trip_doc = await trips_collection.find_one({"trip_code": trip_id.upper()})
        
        if not trip_doc:
            raise HTTPException(status_code=404, detail=f"Trip {trip_id} not found")
        
        # Get phase tracking
        phase_tracking = trip_doc.get("phase_tracking", {})
        phases = phase_tracking.get("phases", {})
        
        if phase not in phases:
            raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")
        
        # Add user to users_ready list
        phase_data = phases[phase]
        users_ready = phase_data.get("users_ready", [])
        
        if user_id not in users_ready:
            users_ready.append(user_id)
        
        # Update phase data
        phase_data["users_ready"] = users_ready
        phases[phase] = phase_data
        phase_tracking["phases"] = phases
        
        # Check if all users ready
        total_members = len(trip_doc.get("members", []))
        all_ready = len(users_ready) >= total_members
        
        # Update in database
        await trips_collection.update_one(
            {"_id": trip_doc["_id"]},
            {
                "$set": {
                    "phase_tracking": phase_tracking,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Broadcast update
        from app.router.chat import broadcast_to_chat
        await broadcast_to_chat(str(trip_doc["_id"]), {
            "type": "phase_ready_update",
            "phase": phase,
            "user_id": user_id,
            "users_ready": users_ready,  # Send full list
            "total_users": total_members,
            "all_ready": all_ready,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # If all ready, trigger Consensus Agent
        if all_ready:
            print(f"[mark_user_ready] All users ready for phase {phase}, triggering Consensus Agent")
            
            # Import and run Consensus Agent
            from app.agents.consensus_agent import ConsensusAgent
            
            consensus = ConsensusAgent()
            initial_state = {
                "trip_id": str(trip_doc["_id"]),
                "agent_data": {},
                "messages": []
            }
            
            # Run in background
            import asyncio
            asyncio.create_task(consensus.run(initial_state))
        
        return APIResponse(
            code=0,
            msg="ok",
            data={
                "phase": phase,
                "users_ready": len(users_ready),
                "total_users": total_members,
                "all_ready": all_ready
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[mark_user_ready] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{trip_id}/phases/unmark-ready", response_model=APIResponse)
async def unmark_user_ready(
    trip_id: str,
    user_id: str,
    phase: str,
):
    """
    Remove user from ready list (allow toggle of Voted button).
    """
    try:
        db = get_database()
        trips_collection = db.trips
        
        # Find trip
        try:
            trip_doc = await trips_collection.find_one({"_id": ObjectId(trip_id)})
        except:
            trip_doc = await trips_collection.find_one({"trip_code": trip_id.upper()})
        
        if not trip_doc:
            raise HTTPException(status_code=404, detail=f"Trip {trip_id} not found")
        
        # Get phase tracking
        phase_tracking = trip_doc.get("phase_tracking", {})
        phases = phase_tracking.get("phases", {})
        
        if phase not in phases:
            raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")
        
        # Remove user from users_ready list
        phase_data = phases[phase]
        users_ready = phase_data.get("users_ready", [])
        
        if user_id in users_ready:
            users_ready.remove(user_id)
        
        # Update phase data
        phase_data["users_ready"] = users_ready
        phases[phase] = phase_data
        phase_tracking["phases"] = phases
        
        # Update in database
        await trips_collection.update_one(
            {"_id": trip_doc["_id"]},
            {
                "$set": {
                    "phase_tracking": phase_tracking,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Broadcast update
        total_members = len(trip_doc.get("members", []))
        from app.router.chat import broadcast_to_chat
        await broadcast_to_chat(str(trip_doc["_id"]), {
            "type": "phase_ready_update",
            "phase": phase,
            "user_id": user_id,
            "users_ready": len(users_ready),
            "total_users": total_members,
            "all_ready": False,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return APIResponse(
            code=0,
            msg="ok",
            data={
                "phase": phase,
                "users_ready": len(users_ready),
                "total_users": total_members,
                "all_ready": False
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[unmark_user_ready] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{trip_id}/itinerary/generate", response_model=APIResponse)
async def generate_itinerary_now(trip_id: str):
    """
    Manually (re)generate itinerary for a trip.
    - Loads current trip + activities from DB
    - Starts orchestrator in background with activity_catalog prefilled
    """
    try:
        db = get_database()
        trips_collection = db.trips
        try:
            trip_doc = await trips_collection.find_one({"_id": ObjectId(trip_id)})
        except Exception:
            trip_doc = await trips_collection.find_one({"trip_code": trip_id.upper()})
        if not trip_doc:
            raise HTTPException(status_code=404, detail=f"Trip {trip_id} not found")

        trip_id_str = str(trip_doc["_id"])
        destination = trip_doc.get("destination")
        trip_duration_days = trip_doc.get("trip_duration_days") or 3
        selected_dates = trip_doc.get("selected_dates")

        # Load activities to pass as catalog (include required activity_id)
        activities_col = get_activities_collection()
        activities = await activities_col.find({"trip_id": trip_id_str}).to_list(length=None)
        # Prefer activities with positive votes; fallback to all if none
        voted = [a for a in activities if (a.get("net_score", 0) or 0) >= 1]
        activities_for_catalog = voted if voted else activities
        activity_catalog: list[dict] = []
        for a in activities_for_catalog:
            act_id = str(a.get("_id") or a.get("name") or "")
            activity_catalog.append({
                "activity_id": act_id,
                "trip_id": trip_id_str,
                "name": a.get("name", ""),
                "category": a.get("category", "Other"),
                "rough_cost": a.get("rough_cost"),
                "duration_min": a.get("duration_min"),
                "lat": a.get("lat"),
                "lng": a.get("lng"),
                "tags": a.get("tags", []),
                "fits": a.get("fits", []),
                "score": a.get("score", 0.0),
                "rationale": a.get("rationale", ""),
                "photo_url": a.get("photo_url"),
            })

        # Kick orchestrator with prefilled catalog to generate itinerary
        import asyncio
        asyncio.create_task(
            run_orchestrator_background(
                trip_id_str, destination, int(trip_duration_days), selected_dates, activity_catalog
            )
        )

        return APIResponse(
            code=0,
            msg="ok",
            data={
                "trip_id": trip_id_str,
                "status": "started",
                "activities": len(activity_catalog),
                "message": "Itinerary generation started. Watch chat for updates."
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[generate_itinerary_now] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start itinerary generation: {str(e)}")

@router.post("/{trip_id}/vote")
async def submit_vote(trip_id: str, vote: VoteRequest):
    """
    Submit a vote during a consensus phase (destination, dates, activities, etc.)
    """
    print(f"[submit_vote] Called for trip_id={trip_id}, user={vote.user_id}, phase={vote.phase}, options={vote.options}")
    try:
        db = get_database()
        trips_collection = db.trips
        
        # Find trip
        try:
            trip_doc = await trips_collection.find_one({"_id": ObjectId(trip_id)})
        except:
            trip_doc = await trips_collection.find_one({"trip_code": trip_id.upper()})
        
        if not trip_doc:
            raise HTTPException(status_code=404, detail="Trip not found")
        
        trip_id_str = str(trip_doc["_id"])
        phase_tracking = trip_doc.get("phase_tracking", {})
        phases = phase_tracking.get("phases", {})
        
        if vote.phase not in phases:
            raise HTTPException(status_code=400, detail=f"Invalid phase: {vote.phase}")
        
        phase_data = phases[vote.phase]
        options = phase_data.get("options", [])
        
        if not options:
            raise HTTPException(status_code=400, detail="No voting options available for this phase")
        
        # Validate all selected options exist
        valid_option_values = {opt["value"] for opt in options}
        for selected_option in vote.options:
            if selected_option not in valid_option_values:
                raise HTTPException(status_code=400, detail=f"Invalid option: {selected_option}")
        
        # Remove user from all options first (clear previous votes)
        for opt in options:
            voters = opt.get("voters", [])
            if vote.user_id in voters:
                voters.remove(vote.user_id)
                opt["voters"] = voters
                opt["votes"] = len(voters)
        
        # Add user to all their selected options (multi-select support)
        for opt in options:
            if opt["value"] in vote.options:
                voters = opt.get("voters", [])
                if vote.user_id not in voters:
                    voters.append(vote.user_id)
                    opt["voters"] = voters
                    opt["votes"] = len(voters)
        
        # Mark user as ready (voting = ready to proceed)
        users_ready = phase_data.get("users_ready", [])
        if vote.user_id not in users_ready:
            users_ready.append(vote.user_id)
        phase_data["users_ready"] = users_ready
        
        # Update database
        phase_data["options"] = options
        phases[vote.phase] = phase_data
        
        await trips_collection.update_one(
            {"_id": trip_doc["_id"]},
            {
                "$set": {
                    f"phase_tracking.phases.{vote.phase}.options": options,
                    f"phase_tracking.phases.{vote.phase}.users_ready": users_ready,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Broadcast vote update to chat
        from app.router.chat import broadcast_to_chat
        await broadcast_to_chat(trip_id_str, {
            "type": "vote_update",
            "phase": vote.phase,
            "options_selected": vote.options,  # Show which options user selected
            "user_id": vote.user_id,
            "options": options,  # Updated vote counts
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Check if all members have voted (track unique voters across all options)
        all_voters = set()
        for opt in options:
            all_voters.update(opt.get("voters", []))
        
        total_members = len(trip_doc.get("members", []))
        
        if len(all_voters) >= total_members:
            # All members voted - check if consensus already triggered
            current_status = phase_data.get("status", "")
            
            if current_status == "active":
                # Consensus already triggered by another concurrent request
                print(f"[vote] All members voted but consensus already active for {vote.phase}")
            else:
                # First to complete voting - trigger consensus agent
                print(f"[vote] All members voted on {vote.phase}, triggering consensus agent")
                
                # Update phase status to active so consensus agent will process it
                await trips_collection.update_one(
                    {"_id": trip_doc["_id"]},
                    {"$set": {f"phase_tracking.phases.{vote.phase}.status": "active"}}
                )
                
                # Trigger consensus in background (don't wait for it)
                async def trigger_consensus_background():
                    from app.agents.orchestrator_agent import run_orchestrator_agent
                    from app.agents.agent_state import AgentState
                    
                    # Reload trip to get updated phase_tracking
                    trip = await trips_collection.find_one({"_id": trip_doc["_id"]})
                    phase_tracking = trip.get("phase_tracking", {})
                    
                    initial_state: AgentState = {
                        "trip_id": trip_id_str,
                        "goal": f"Resolve consensus for {vote.phase}",
                        "agent_data": {
                            "destination": trip.get("destination"),
                            "trip_duration_days": trip.get("trip_duration_days"),
                            "phase_tracking": phase_tracking,
                        },
                        "messages": [],
                    }
                    
                    await run_orchestrator_agent(initial_state)
                
                # Fire and forget - don't await
                asyncio.create_task(trigger_consensus_background())
    
        return APIResponse(
            code=0,
            msg="Vote recorded successfully",
            data={
                "phase": vote.phase,
                "options": options,
                "total_members": total_members,
                "voted_members": len(all_voters)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[submit_vote] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{trip_id}/itinerary", response_model=APIResponse)
async def get_trip_itinerary(trip_id: str):
    """
    Get the current itinerary for a trip.
    Returns the most recent itinerary version marked as is_current=True.
    """
    try:
        from app.db.database import get_itineraries_collection
        
        itineraries_collection = get_itineraries_collection()
        
        # Find the current itinerary for this trip
        itinerary = await itineraries_collection.find_one(
            {"trip_id": trip_id, "is_current": True},
            sort=[("version", -1)]  # Get the latest version
        )
        
        if not itinerary:
            return APIResponse(
                code=404,
                msg="No itinerary found for this trip",
                data=None
            )
        
        # Convert ObjectId to string
        if "_id" in itinerary:
            itinerary["_id"] = str(itinerary["_id"])

        # Append activity data into each itinerary item for convenience on the client
        # We keep itinerary storage lean (only ids + schedule), but enrich on read.
        try:
            activities_col = get_activities_collection()
            activities = await activities_col.find({"trip_id": trip_id}).to_list(length=None)
            id_to_activity = {str(a.get("_id")): a for a in activities if a.get("_id")}
            name_to_activity = {str(a.get("name", "")).strip().lower(): a for a in activities if a.get("name")}

            for day in itinerary.get("days", []) or []:
                for item in day.get("items", []) or []:
                    act = None
                    act_id = item.get("activity_id")
                    if act_id and act_id in id_to_activity:
                        act = id_to_activity[act_id]
                    else:
                        # Fallback join by name if id not present (older data)
                        nm = str(item.get("name", "")).strip().lower()
                        if nm:
                            act = name_to_activity.get(nm)

                    if not act:
                        continue

                    # Only fill in missing or optional fields to avoid clobbering edits
                    if not item.get("name") and act.get("name") is not None:
                        item["name"] = act.get("name")
                    if act.get("category") is not None:
                        item["category"] = act.get("category")
                    if act.get("lat") is not None:
                        item["lat"] = act.get("lat")
                    if act.get("lng") is not None:
                        item["lng"] = act.get("lng")
                    if act.get("rough_cost") is not None:
                        item["rough_cost"] = act.get("rough_cost")
                    if act.get("duration_min") is not None:
                        item["duration_min"] = act.get("duration_min")
        except Exception as e:
            # Non-fatal: continue returning the itinerary even if enrichment fails
            print(f"[get_trip_itinerary] Warning: failed to append activity data: {e}")

        return APIResponse(
            code=0,
            msg="ok",
            data=itinerary
        )
        
    except Exception as e:
        print(f"[get_trip_itinerary] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))