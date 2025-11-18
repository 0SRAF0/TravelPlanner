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


async def run_orchestrator_background(
    trip_id: str, destination: str, trip_duration_days: int, selected_dates: str
):
    """
    Run the orchestrator agent in the background and broadcast updates to chat.
    """
    from app.agents.orchestrator_agent import run_orchestrator_agent

    db = get_database()
    messages_collection = db.messages

    # Helper function to broadcast agent status
    async def broadcast_agent_status(agent_name: str, status: str, step: str):
        from app.router.chat import broadcast_to_chat

        await broadcast_to_chat(
            trip_id,
            {
                "type": "agent_status",
                "agent_name": agent_name,
                "status": status,
                "step": step,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    # Send initial status
    await broadcast_agent_status("Orchestrator", "starting", "Initializing trip planning")

    # Send initial message to chat
    await messages_collection.insert_one(
        {
            "chatId": trip_id,
            "senderId": "system",
            "senderName": "AI Assistant",
            "content": f"🚀 Starting trip planning...\nDestination: {destination or 'TBD'}\nDuration: {trip_duration_days} days\nDates: {selected_dates or 'Flexible'}",
            "type": "ai",
            "createdAt": datetime.utcnow(),
        }
    )

    # Broadcast to active WebSocket connections
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

    # Update status: analyzing preferences
    await broadcast_agent_status("Preference Agent", "running", "Analyzing group preferences")

    # Run orchestrator
    initial_state = {
        "trip_id": trip_id,
        "goal": f"Plan a {trip_duration_days}-day trip to {destination}",
        "agent_data": {
            "destination": destination,
            "trip_duration_days": trip_duration_days,
        },
    }

    try:
        # Update status: destination research
        await broadcast_agent_status(
            "Destination Research Agent", "running", "Researching destinations and attractions"
        )

        # Simulate some processing time and update status
        import asyncio

        await asyncio.sleep(2)

        # Update status: itinerary planning
        await broadcast_agent_status("Itinerary Agent", "running", "Creating day-by-day itinerary")

        result = await run_orchestrator_agent(initial_state)

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
                    print(
                        f"[orchestrator_background] Saved {len(res.inserted_ids)} activities for trip={trip_id}"
                    )
        except Exception as e:
            print(f"[orchestrator_background] Warning: failed to save activities after orchestrator: {e}")

        # Update status: completed
        await broadcast_agent_status("Orchestrator", "completed", "Trip planning finished")

        # Send completion message
        success_msg = f"✅ Trip planning complete!\nSteps taken: {result.get('steps', 0)}\nStatus: {result.get('reason', 'Done')}"
        await messages_collection.insert_one(
            {
                "chatId": trip_id,
                "senderId": "system",
                "senderName": "AI Assistant",
                "content": success_msg,
                "type": "ai",
                "createdAt": datetime.utcnow(),
            }
        )

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

        print(f"[orchestrator_background] Completed for trip {trip_id}")

    except Exception as e:
        # Update status: error
        await broadcast_agent_status("Orchestrator", "error", f"Failed: {str(e)}")

        error_msg = f"❌ Planning failed: {str(e)}\nPlease try again or contact support."
        await messages_collection.insert_one(
            {
                "chatId": trip_id,
                "senderId": "system",
                "senderName": "AI Assistant",
                "content": error_msg,
                "type": "ai",
                "createdAt": datetime.utcnow(),
            }
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

        print(f"[orchestrator_background] Failed for trip {trip_id}: {e}")


class CreateTripRequest(BaseModel):
    trip_name: str = Field(..., description="Name for the trip")
    creator_id: str = Field(..., description="User ID of the creator")
    destination: str = Field(..., description="Destination for the trip")


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

        destination = trip_doc.get("destination")

        # Update trip with aggregated values
        await trips_collection.update_one(
            {"_id": trip_doc["_id"]},
            {
                "$set": {
                    "destination": destination,
                    "trip_duration_days": trip_duration_days,
                    "selected_dates": selected_dates,
                    "status": "planning",
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        print(f"[all_in] Starting orchestrator for trip {trip_id_str}")
        print(f"  Destination: {destination}")
        print(f"  Duration: {trip_duration_days} days")
        print(f"  Selected dates: {selected_dates}")
        print(f"  Members with preferences: {len(members_with_prefs)}/{len(members)}")

        # Preference ingestion and aggregation, plus optional destination research
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