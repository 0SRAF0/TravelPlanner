"""
Consensus Agent - Handles group decision-making and voting
"""

from typing import Any, Dict, List
from datetime import datetime
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, END
from app.agents.agent_state import AgentState
from app.db.database import get_database, get_activities_collection
from bson import ObjectId


class ConsensusAgent:
    """
    Handles consensus-building and decision-making across all phases.
    Tracks fairness to ensure no one compromises on everything.
    """
    
    def __init__(self):
        self.app = self._build_graph()
    
    async def _make_phase_decision(self, state: AgentState) -> AgentState:
        """
        Make decision for current phase based on votes and discussion.
        """
        trip_id = state.get("trip_id")
        agent_data = state.get("agent_data", {}) or {}
        
        if not trip_id:
            return {"done": True, "messages": [AIMessage(content="[consensus] No trip_id")]}
        
        print(f"\n[consensus] Making decision for trip {trip_id}")
        
        try:
            db = get_database()
            trips = db.trips
            
            # Get trip with phase tracking
            try:
                trip = await trips.find_one({"_id": ObjectId(trip_id)})
            except:
                trip = await trips.find_one({"trip_code": trip_id.upper()})
            
            if not trip:
                return {"done": True, "messages": [AIMessage(content="[consensus] Trip not found")]}
            
            phase_tracking = trip.get("phase_tracking", {})
            current_phase = phase_tracking.get("current_phase", "activity_voting")
            phases = phase_tracking.get("phases", {})
            
            print(f"[consensus] Current phase: {current_phase}")
            
            # Route to appropriate decision handler
            if current_phase == "activity_voting":
                return await self._decide_activities(trip_id, trip, phases, agent_data)
            elif current_phase == "destination_decision":
                return await self._decide_destination(trip_id, trip, phases, agent_data)
            elif current_phase == "date_selection":
                return await self._decide_dates(trip_id, trip, phases, agent_data)
            elif current_phase == "itinerary_approval":
                return await self._finalize_itinerary(trip_id, trip, phases, agent_data)
            else:
                return {"done": True, "messages": [AIMessage(content=f"[consensus] Unknown phase: {current_phase}")]}
                
        except Exception as e:
            print(f"[consensus] Error: {e}")
            return {"done": True, "messages": [AIMessage(content=f"[consensus] Error: {e}")]}
    
    async def _decide_activities(
        self, 
        trip_id: str, 
        trip: dict, 
        phases: dict,
        agent_data: dict
    ) -> AgentState:
        """
        Select activities based on votes, discussion, and fairness.
        """
        print(f"[consensus] Deciding activities for trip {trip_id}")
        
        # Check if all users are ready before making decision
        phase_data = phases.get("activity_voting", {})
        users_ready = phase_data.get("users_ready", [])
        total_members = len(trip.get("members", []))
        
        print(f"[consensus] Activity voting readiness: {len(users_ready)}/{total_members} members ready")
        
        if len(users_ready) < total_members:
            print(f"[consensus] Waiting for remaining {total_members - len(users_ready)} members to mark ready...")
            return {
                "agent_data": agent_data,
                "done": True,
                "messages": [AIMessage(content=f"[consensus] Waiting for all members to finish voting on activities ({len(users_ready)}/{total_members})")]
            }
        
        print(f"[consensus] ✅ All members ready! Selecting activities...")
        
        # Get all activities with votes
        col = get_activities_collection()
        activities = await col.find({"trip_id": trip_id}).to_list(length=None)
        
        if not activities:
            print("[consensus] No activities found")
            return {"done": True, "messages": [AIMessage(content="[consensus] No activities to select from")]}
        
        # Score activities
        scored_activities = []
        for activity in activities:
            score = 0
            
            # Net votes (primary factor)
            net_score = activity.get("net_score", 0)
            score += net_score * 10
            
            # Original AI score
            original_score = activity.get("score", 0)
            score += original_score * 50
            
            # Strong downvotes (heavy penalty)
            downvote_count = activity.get("downvote_count", 0)
            if downvote_count >= 2:  # 2+ people hate it
                score -= 30
            
            activity["final_score"] = score
            scored_activities.append(activity)
        
        # Sort by score
        scored_activities.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        
        # Select top 35 with category balance
        # IMPORTANT: honor votes — include only activities with positive net votes
        selected = []
        category_counts = {}
        
        for activity in scored_activities:
            category = activity.get("category", "Other")
            
            # Max 7 per category for balance
            if category_counts.get(category, 0) >= 7:
                continue

            # Require at least one more upvote than downvote (net_score >= 1)
            if (activity.get("net_score", 0) or 0) < 1:
                continue

            selected.append(activity)
            category_counts[category] = category_counts.get(category, 0) + 1
            
            if len(selected) >= 35:
                break
        
        print(f"[consensus] Selected {len(selected)} activities")
        
        # Update agent_data with selection
        # Include IDs for downstream filtering
        agent_data["selected_activity_ids"] = [
            str(a.get("_id") or a.get("activity_id") or "")
            for a in selected
            if (a.get("_id") or a.get("activity_id"))
        ]
        agent_data["selected_activities"] = [
            {
                "activity_id": str(a.get("_id") or a.get("activity_id") or ""),
                "name": a.get("name"),
                "category": a.get("category"),
                "score": a.get("final_score"),
                "net_score": a.get("net_score", 0),
            }
            for a in selected
        ]
        
        # Broadcast decision to chat
        from app.router.chat import broadcast_to_chat
        await broadcast_to_chat(trip_id, {
            "senderId": "system",
            "senderName": "AI Assistant",
            "content": f"✅ Activities selected! I've chosen {len(selected)} activities based on your votes and preferences.\n\nReady to create your itinerary!",
            "type": "ai",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Mark phase as completed
        db = get_database()
        trips = db.trips
        phases["activity_voting"]["status"] = "completed"
        phases["activity_voting"]["completed_at"] = datetime.utcnow()
        
        await trips.update_one(
            {"_id": ObjectId(trip_id)},
            {
                "$set": {
                    "phase_tracking.phases": phases,
                    # Auto-complete itinerary approval: no approval gate
                    "phase_tracking.current_phase": None,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Trigger orchestrator to generate itinerary (no approval step)
        print(f"[consensus] Triggering orchestrator for itinerary generation")
        import asyncio
        asyncio.create_task(self._trigger_orchestrator_for_itinerary(trip_id, trip, agent_data))
        
        return {
            "agent_data": agent_data,
            "done": True,
            "messages": [AIMessage(content=f"[consensus] Selected {len(selected)} activities")]
        }
    
    async def _trigger_orchestrator_for_itinerary(self, trip_id: str, trip: dict, agent_data: dict):
        """Trigger orchestrator to generate itinerary after activity voting completes"""
        from app.agents.orchestrator_agent import run_orchestrator_agent
        from app.agents.agent_state import AgentState
        
        print(f"[consensus] Starting orchestrator for itinerary generation (trip {trip_id})")
        
        # Reload trip to get updated phase_tracking
        db = get_database()
        trips = db.trips
        updated_trip = await trips.find_one({"_id": ObjectId(trip_id)})
        
        if not updated_trip:
            print(f"[consensus] ERROR: Trip {trip_id} not found for itinerary generation")
            return
        
        phase_tracking = updated_trip.get("phase_tracking", {})
        
        # Load activities from database to pass to orchestrator
        col = get_activities_collection()
        activities = await col.find({"trip_id": trip_id}).to_list(length=None)
        
        # Filter to only selected activity IDs (fallback to positive-vote items)
        selected_ids = set([s for s in (agent_data.get("selected_activity_ids") or []) if s])
        if selected_ids:
            activities = [a for a in activities if str(a.get("_id")) in selected_ids]
            print(f"[consensus] Filtering activities to selected IDs: {len(activities)} remain")
        else:
            # Fallback: keep only activities with positive net_score
            pos = [a for a in activities if (a.get("net_score", 0) or 0) >= 1]
            if pos:
                print(f"[consensus] No explicit selected IDs; using {len(pos)} activities with positive votes")
                activities = pos
            else:
                print(f"[consensus] No positive-vote activities; using top activities by score (fallback)")

        # Convert to activity_catalog format
        activity_catalog = []
        for activity in activities:
            # Ensure required activity_id for itinerary agent
            act_id = str(activity.get("_id") or activity.get("activity_id") or activity.get("name") or "")
            activity_catalog.append({
                "activity_id": act_id,
                "trip_id": trip_id,
                "name": activity.get("name", ""),
                "category": activity.get("category", "Other"),
                "rough_cost": activity.get("rough_cost"),
                "duration_min": activity.get("duration_min"),
                "lat": activity.get("lat"),
                "lng": activity.get("lng"),
                "tags": activity.get("tags", []),
                "fits": activity.get("fits", []),
                "score": activity.get("score", 0.0),
                "rationale": activity.get("rationale", ""),
                "photo_url": activity.get("photo_url"),
            })
        
        print(f"[consensus] Loaded {len(activity_catalog)} activities for itinerary generation")

        # Derive start_date from trip.selected_dates if available ("YYYY-MM-DD:YYYY-MM-DD")
        start_date: str | None = None
        try:
            selected_dates_val = updated_trip.get("selected_dates")
            if isinstance(selected_dates_val, str) and ":" in selected_dates_val:
                start_date = selected_dates_val.split(":", 1)[0]
        except Exception:
            start_date = None
        
        initial_state: AgentState = {
            "trip_id": trip_id,
            "goal": "Generate itinerary from selected activities",
            "agent_data": {
                "destination": updated_trip.get("destination"),
                "trip_duration_days": updated_trip.get("trip_duration_days"),
                "start_date": start_date,
                "phase_tracking": phase_tracking,
                "activity_catalog": activity_catalog,
                "selected_activities": agent_data.get("selected_activities"),
            },
            # Provide start_date at top-level too
            "start_date": start_date,
            "messages": [],
        }
        
        print(f"[consensus] Calling run_orchestrator_agent for itinerary...")
        await run_orchestrator_agent(initial_state)
    
    async def _decide_destination(self, trip_id: str, trip: dict, phases: dict, agent_data: dict) -> AgentState:
        """Decide destination based on preferences and discussion"""
        print(f"[consensus] Deciding destination for trip {trip_id}")
        
        db = get_database()
        prefs_col = db.preferences
        trips_col = db.trips
        
        # Get all preferences
        preferences = await prefs_col.find({"trip_id": trip_id}).to_list(length=None)
        
        if not preferences:
            print("[consensus] No preferences found")
            return {"done": True, "messages": [AIMessage(content="[consensus] No preferences to decide from")]}
        
        # Count destination votes
        from collections import Counter
        dest_votes = Counter()
        for pref in preferences:
            dest = pref.get("destination")
            if dest:
                dest_votes[dest.strip().lower()] = dest_votes.get(dest.strip().lower(), 0) + 1
        
        if not dest_votes:
            print("[consensus] No destinations provided")
            return {"done": True, "messages": [AIMessage(content="[consensus] No destinations provided")]}
        
        # Get most common
        most_common = dest_votes.most_common()
        
        # Check for tie
        if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
            # Tie detected - check if we have voting results
            tied = [d for d, count in most_common if count == most_common[0][1]]
            print(f"[consensus] Destination tie detected: {tied}")
            
            # Check if phase already has voting options set up
            phase_data = phases.get("destination_decision", {})
            existing_options = phase_data.get("options", [])
            
            if not existing_options:
                # First time seeing this tie - set up voting
                print(f"[consensus] Setting up voting for destinations: {tied}")
                
                voting_options = [
                    {"value": dest, "label": dest.title(), "votes": 0, "voters": []}
                    for dest in tied
                ]
                
                phases["destination_decision"]["options"] = voting_options
                phases["destination_decision"]["status"] = "voting_in_progress"
                await trips_col.update_one(
                    {"_id": ObjectId(trip_id)},
                    {
                        "$set": {
                            "phase_tracking.phases.destination_decision.options": voting_options,
                            "phase_tracking.phases.destination_decision.status": "voting_in_progress"
                        }
                    }
                )
                
                # Broadcast voting request to chat
                from app.router.chat import broadcast_to_chat
                options_text = " or ".join([f"**{d.title()}**" for d in tied])
                await broadcast_to_chat(trip_id, {
                    "senderId": "system",
                    "senderName": "AI Assistant",
                    "content": f"🗳️ We have a tie between {options_text}!\n\nPlease vote for your preferred destination.",
                    "type": "voting",
                    "phase": "destination_decision",
                    "options": voting_options,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                # Keep phase active - waiting for votes
                return {
                    "agent_data": agent_data,
                    "done": True,
                    "messages": [AIMessage(content=f"[consensus] Waiting for destination votes")]
                }
            else:
                # Voting already set up - check if we have votes
                print(f"[consensus] Checking voting results...")
                
                # Count votes from options
                vote_counts = {opt["value"]: len(opt.get("voters", [])) for opt in existing_options}
                
                if sum(vote_counts.values()) == 0:
                    # No votes yet, keep waiting - ensure status is voting_in_progress
                    print(f"[consensus] No votes received yet, waiting...")
                    if phase_data.get("status") != "voting_in_progress":
                        await trips_col.update_one(
                            {"_id": ObjectId(trip_id)},
                            {"$set": {"phase_tracking.phases.destination_decision.status": "voting_in_progress"}}
                        )
                    return {
                        "agent_data": agent_data,
                        "done": True,
                        "messages": [AIMessage(content=f"[consensus] Waiting for destination votes")]
                    }
                
                # Check if all users have voted before making decision
                all_voters = set()
                for opt in existing_options:
                    all_voters.update(opt.get("voters", []))
                
                total_members = len(trip.get("members", []))
                print(f"[consensus] Vote progress: {len(all_voters)}/{total_members} members voted")
                
                if len(all_voters) < total_members:
                    # Not everyone has voted yet - keep waiting
                    print(f"[consensus] Waiting for remaining {total_members - len(all_voters)} members to vote...")
                    return {
                        "agent_data": agent_data,
                        "done": True,
                        "messages": [AIMessage(content=f"[consensus] Waiting for all members to vote ({len(all_voters)}/{total_members})")]
                    }
                
                # All users voted - now make decision
                print(f"[consensus] ✅ All members voted! Determining winner...")
                
                # Use majority rule - most votes wins
                max_votes = max(vote_counts.values())
                winners = [dest for dest, count in vote_counts.items() if count == max_votes]
                
                if len(winners) == 1:
                    # Clear winner
                    selected_dest = winners[0]
                    print(f"[consensus] Voting winner: {selected_dest} with {max_votes} votes")
                elif len(winners) > 1:
                    # Still tied even after voting - pick randomly
                    import random
                    selected_dest = random.choice(winners)
                    print(f"[consensus] Still tied after voting ({winners}), randomly choosing: {selected_dest}")
                else:
                    selected_dest = winners[0]
                
                # Broadcast result
                from app.router.chat import broadcast_to_chat
                await broadcast_to_chat(trip_id, {
                    "senderId": "system",
                    "senderName": "AI Assistant",
                    "content": f"✅ Voting complete! **{selected_dest.title()}** wins with {vote_counts[selected_dest]} votes.",
                    "type": "ai",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                # Continue with selected_dest (fall through to winner logic below)
        else:
            # Clear winner
            selected_dest = most_common[0][0]
            print(f"[consensus] Selected destination: {selected_dest} ({most_common[0][1]} votes)")
        
        # Broadcast decision
        from app.router.chat import broadcast_to_chat
        await broadcast_to_chat(trip_id, {
            "senderId": "system",
            "senderName": "AI Assistant",
            "content": f"✅ Destination selected: **{selected_dest.title()}**!\n\nLet's continue planning your trip.",
            "type": "ai",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Mark destination phase as completed
        phases["destination_decision"]["status"] = "completed"
        phases["destination_decision"]["completed_at"] = datetime.utcnow()
        
        # Check if dates need consensus next
        date_phase = phases.get("date_selection", {})
        date_status = date_phase.get("status")
        date_options = date_phase.get("date_options", [])
        
        print(f"[consensus] Checking if date consensus needed:")
        print(f"  - date_phase status: {date_status}")
        print(f"  - date_options: {date_options}")
        
        needs_date_consensus = date_status == "pending" and len(date_options) > 0
        
        # Determine next phase
        next_phase = "date_selection" if needs_date_consensus else None
        print(f"  - needs_date_consensus: {needs_date_consensus}")
        print(f"  - next_phase: {next_phase}")
        
        # Update trip: set destination and move to next phase or clear
        update_doc = {
            "$set": {
                "destination": selected_dest,  # Critical: update destination in trip doc
                "phase_tracking.phases.destination_decision.status": "completed",
                "phase_tracking.phases.destination_decision.completed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        }
        
        if next_phase:
            # Move to date selection phase
            print(f"[consensus] ✅ Destination resolved: {selected_dest}. Moving to date selection phase.")
            update_doc["$set"]["phase_tracking.current_phase"] = "date_selection"
            update_doc["$set"]["phase_tracking.phases.date_selection.status"] = "active"
            update_doc["$set"]["phase_tracking.phases.date_selection.started_at"] = datetime.utcnow()
        else:
            # No more consensus needed - clear current_phase
            print(f"[consensus] ✅ Destination resolved: {selected_dest}. No date conflicts. Proceeding to destination research.")
            update_doc["$unset"] = {"phase_tracking.current_phase": ""}
        
        await trips_col.update_one({"_id": ObjectId(trip_id)}, update_doc)
        
        # UPDATE AGENT_DATA WITH SELECTED DESTINATION
        agent_data["destination"] = selected_dest
        
        # Update phase_tracking in agent_data to reflect current state
        if next_phase:
            # Keep phase_tracking so orchestrator routes back to consensus for dates
            phases["date_selection"]["status"] = "active"
            phases["date_selection"]["started_at"] = datetime.utcnow()
            agent_data["phase_tracking"] = {
                "current_phase": "date_selection",
                "phases": phases
            }
        else:
            # Clear current_phase - no more consensus needed, but keep phase structure
            print(f"[consensus] Clearing current_phase - ready for destination research")
            agent_data["phase_tracking"] = {
                "current_phase": None,
                "phases": phases
            }
        
        return {
            "agent_data": agent_data,
            "done": True,
            "messages": [AIMessage(content=f"[consensus] Selected destination: {selected_dest}")]
        }
    
    async def _decide_dates(self, trip_id: str, trip: dict, phases: dict, agent_data: dict) -> AgentState:
        """Decide dates through voting when there's a conflict."""
        print(f"[consensus] Deciding dates for trip {trip_id}")
        
        db = get_database()
        trips_col = db.trips
        
        phase_data = phases.get("date_selection", {})
        date_options = phase_data.get("date_options", [])
        
        if not date_options:
            print("[consensus] No date options found - nothing to decide")
            return {"done": True, "messages": [AIMessage(content="[consensus] No date options to decide")]}
        
        print(f"[consensus] Date options: {date_options}")
        
        # Check if voting has been set up
        existing_options = phase_data.get("options", [])
        
        if not existing_options:
            # First time - set up voting
            print(f"[consensus] Setting up voting for dates: {date_options}")
            
            voting_options = [
                {
                    "label": f"{opt.split(':')[0]} to {opt.split(':')[1]}",
                    "value": opt,
                    "votes": 0,
                    "voters": []
                }
                for opt in date_options
            ]
            
            # Update DB with voting options
            await trips_col.update_one(
                {"_id": ObjectId(trip_id)},
                {
                    "$set": {
                        "phase_tracking.phases.date_selection.options": voting_options,
                        "phase_tracking.phases.date_selection.status": "voting_in_progress",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # Broadcast voting UI to chat
            from app.router.chat import broadcast_to_chat
            await broadcast_to_chat(trip_id, {
                "senderId": "system",
                "senderName": "AI Assistant",
                "content": f"📅 **Date Conflict Detected!**\n\nMultiple date ranges have equal votes. Please vote on your preferred dates:",
                "type": "voting",
                "phase": "date_selection",
                "options": voting_options,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Update agent_data to keep phase tracking
            agent_data["phase_tracking"] = {
                "current_phase": "date_selection",
                "phases": phases
            }
            
            return {
                "agent_data": agent_data,
                "done": True,
                "messages": [AIMessage(content=f"[consensus] Waiting for date votes")]
            }
        else:
            # Voting already set up - check results
            print(f"[consensus] Checking date voting results...")
            
            vote_counts = {opt["value"]: len(opt.get("voters", [])) for opt in existing_options}
            
            if sum(vote_counts.values()) == 0:
                # No votes yet
                print(f"[consensus] No votes received yet, waiting...")
                if phase_data.get("status") != "voting_in_progress":
                    await trips_col.update_one(
                        {"_id": ObjectId(trip_id)},
                        {"$set": {"phase_tracking.phases.date_selection.status": "voting_in_progress"}}
                    )
                return {
                    "agent_data": agent_data,
                    "done": True,
                    "messages": [AIMessage(content=f"[consensus] Waiting for date votes")]
                }
            
            # Check if all users have voted before making decision
            all_voters = set()
            for opt in existing_options:
                all_voters.update(opt.get("voters", []))
            
            total_members = len(trip.get("members", []))
            print(f"[consensus] Date vote progress: {len(all_voters)}/{total_members} members voted")
            
            if len(all_voters) < total_members:
                # Not everyone has voted yet - keep waiting
                print(f"[consensus] Waiting for remaining {total_members - len(all_voters)} members to vote on dates...")
                return {
                    "agent_data": agent_data,
                    "done": True,
                    "messages": [AIMessage(content=f"[consensus] Waiting for all members to vote on dates ({len(all_voters)}/{total_members})")]
                }
            
            # All users voted - now make decision
            print(f"[consensus] ✅ All members voted on dates! Determining winner...")
            
            # Use majority rule - most votes wins
            max_votes = max(vote_counts.values())
            winners = [date_range for date_range, count in vote_counts.items() if count == max_votes]
            
            if len(winners) == 1:
                # Clear winner
                selected_dates = winners[0]
                print(f"[consensus] Voting winner: {selected_dates} with {max_votes} votes")
            else:
                # Still tied - pick randomly
                import random
                selected_dates = random.choice(winners)
                print(f"[consensus] Still tied after voting ({winners}), randomly choosing: {selected_dates}")
            
            # Calculate duration
            from datetime import datetime as dt
            try:
                start_str, end_str = selected_dates.split(":")
                start_date = dt.fromisoformat(start_str)
                end_date = dt.fromisoformat(end_str)
                trip_duration_days = (end_date - start_date).days + 1
            except Exception as e:
                print(f"[consensus] Error parsing dates: {e}")
                trip_duration_days = 7  # Fallback
            
            # Broadcast result
            from app.router.chat import broadcast_to_chat
            await broadcast_to_chat(trip_id, {
                "senderId": "system",
                "senderName": "AI Assistant",
                "content": f"✅ Voting complete! **{selected_dates.replace(':', ' to ')}** wins with {vote_counts[selected_dates]} votes.",
                "type": "ai",
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Mark date phase as completed and clear current_phase
            await trips_col.update_one(
                {"_id": ObjectId(trip_id)},
                {
                    "$set": {
                        "selected_dates": selected_dates,
                        "trip_duration_days": trip_duration_days,
                        "phase_tracking.phases.date_selection.status": "completed",
                        "phase_tracking.phases.date_selection.completed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    },
                    "$unset": {
                        "phase_tracking.current_phase": ""  # Clear - all conflicts resolved
                    }
                }
            )
            
            # Update agent_data - clear phase_tracking now that all conflicts resolved
            agent_data["selected_dates"] = selected_dates
            agent_data["trip_duration_days"] = trip_duration_days
            agent_data["phase_tracking"] = None  # All consensus phases complete
            
            print(f"[consensus] ✅ Dates resolved: {selected_dates}. All conflicts resolved. Proceeding to destination research.")
            
            return {
                "agent_data": agent_data,
                "done": True,
                "messages": [AIMessage(content=f"[consensus] Selected dates: {selected_dates}")]
            }
    
    async def _finalize_itinerary(self, trip_id: str, trip: dict, phases: dict, agent_data: dict) -> AgentState:
        """Finalize itinerary after all users approve"""
        print(f"[consensus] Finalizing itinerary for trip {trip_id}")
        
        # Check if all users are ready before finalizing
        phase_data = phases.get("itinerary_approval", {})
        users_ready = phase_data.get("users_ready", [])
        total_members = len(trip.get("members", []))
        
        print(f"[consensus] Itinerary approval readiness: {len(users_ready)}/{total_members} members ready")
        
        if len(users_ready) < total_members:
            print(f"[consensus] Waiting for remaining {total_members - len(users_ready)} members to approve...")
            return {
                "agent_data": agent_data,
                "done": True,
                "messages": [AIMessage(content=f"[consensus] Waiting for all members to approve itinerary ({len(users_ready)}/{total_members})")]
            }
        
        print(f"[consensus] ✅ All members approved! Finalizing itinerary...")
        
        # Mark phase as completed
        db = get_database()
        trips = db.trips
        phases["itinerary_approval"]["status"] = "completed"
        phases["itinerary_approval"]["completed_at"] = datetime.utcnow()
        
        await trips.update_one(
            {"_id": ObjectId(trip_id)},
            {
                "$set": {
                    "phase_tracking.phases.itinerary_approval": phases["itinerary_approval"],
                    "phase_tracking.current_phase": None,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Broadcast completion
        from app.router.chat import broadcast_to_chat
        await broadcast_to_chat(trip_id, {
            "senderId": "system",
            "senderName": "AI Assistant",
            "content": f"🎉 **Trip Planning Complete!**\n\nYour itinerary has been approved by all members. Have a great trip!",
            "type": "ai",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "agent_data": agent_data,
            "done": True,
            "messages": [AIMessage(content="[consensus] Itinerary finalized")]
        }
    
    def _build_graph(self) -> StateGraph:
        """Build LangGraph state machine"""
        g = StateGraph(AgentState)
        g.add_node("make_decision", self._make_phase_decision)
        g.set_entry_point("make_decision")
        g.add_edge("make_decision", END)
        return g.compile()
    
    async def run(self, initial_state: dict[str, Any]) -> dict[str, Any]:
        """Run the consensus agent"""
        return await self.app.ainvoke(initial_state)


__all__ = ["ConsensusAgent"]