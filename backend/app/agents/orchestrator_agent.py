# orchestrator_agent.py - Multi-agent orchestrator for travel planner
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic.v1 import BaseModel, Field

from app.agents.agent_state import AgentState
from app.agents.destination_research_agent import DestinationResearchAgent
from app.agents.itinerary_agent import ItineraryAgent
from app.agents.preference_agent import PreferenceAgent
from app.agents.consensus_agent import ConsensusAgent
from app.core.config import OPEN_AI_MODEL, OPEN_AI_API_KEY

# --- Instantiate agents ---
preference_agent = PreferenceAgent()
destination_research_agent = DestinationResearchAgent()
itinerary_agent = ItineraryAgent()
consensus_agent = ConsensusAgent()

# --- Worker registry: add new agents here later ---
WORKERS: dict[str, dict[str, str]] = {
    # key -> graph node name + description
    "preference_processor": {
        "node": "preference_agent",
        "desc": "Process and save user travel preferences (budget, vibes, deal breakers)",
    },
    "consensus_resolver": {
        "node": "consensus_agent",
        "desc": "Resolve conflicts through voting when users disagree on destination, dates, activities, or itinerary",
    },
    "destination_researcher": {
        "node": "destination_research_agent",
        "desc": "Research destination and generate activity catalog aligned to group preferences",
    },
    "itinerary_planner": {
        "node": "itinerary_agent",
        "desc": "Generate trip itinerary based on preferences and activity catalog",
    },
    # Future agents:
    # "accommodation_finder": {"node": "accommodation_agent", "desc": "Find suitable accommodations"},
}

# --- LLM for supervision ---
try:
    # Prefer explicit API key; avoid ADC requirement in local/dev
    llm = (
        ChatOpenAI(
            model=OPEN_AI_MODEL, 
            api_key=OPEN_AI_API_KEY,
            max_retries=0  # Disable LangChain's retry - let agents handle retries
        )
        if OPEN_AI_API_KEY
        else None
    )
except Exception:
    llm = None


class SupervisorChoice(BaseModel):
    next_task: str = Field(
        description=f"Choose one of: {', '.join(list(WORKERS.keys()) + ['end'])}"
    )
    reason: str


SUPERVISOR_SYS = """
You are the Travel Planner Workflow Supervisor.
Goal: Route to the best next agent given the current state and goal.
Choose `next_task` from the allowed registry keys or 'end' if all relevant tasks are done.

Registry (key → capability):
{registry_block}

Routing rules:
1) If trip_id exists and no preferences_summary → preference_processor (fetch and aggregate)
2) If phase_tracking exists and current_phase requires consensus → consensus_resolver (resolve conflicts through voting)
3) If preferences_summary exists, destination provided, and no activity_catalog → destination_researcher
4) If activity_catalog exists, trip_duration_days is set, and no itinerary → itinerary_planner
5) If all relevant items are done or goal accomplished → end

Return JSON only.
"""


def _needs_preference_processing(state: AgentState) -> bool:
    """Check if preferences need to be fetched and processed."""
    # Check if we have a trip_id and haven't processed yet
    trip_id = state.get("trip_id")
    agent_data = state.get("agent_data", {}) or {}
    has_summary = agent_data.get("preferences_summary") is not None
    result = bool(trip_id) and not has_summary
    if result:
        print(f"[orchestrator] Preference processing needed for trip {trip_id}")
    return result


def _needs_consensus(state: AgentState) -> bool:
    """Check if consensus is needed to resolve user conflicts."""
    agent_data = state.get("agent_data", {}) or {}
    phase_tracking = agent_data.get("phase_tracking")
    
    print(f"\n[orchestrator] ======= _needs_consensus check =======")
    print(f"[orchestrator] phase_tracking = {phase_tracking}")
    
    if not phase_tracking:
        print(f"[orchestrator] No phase_tracking found - no consensus needed")
        return False
    
    current_phase = phase_tracking.get("current_phase")
    print(f"[orchestrator] current_phase = {current_phase}")
    
    # If current_phase is None or empty, consensus is complete
    if not current_phase:
        print(f"[orchestrator] No active consensus phase - proceeding with normal flow")
        return False
    
    phases = phase_tracking.get("phases", {})
    
    # Check if current phase requires consensus and isn't completed
    if current_phase in phases:
        phase_data = phases[current_phase]
        status = phase_data.get("status")
        print(f"[orchestrator] Phase '{current_phase}' has status: {status}")
        # Special handling: for phases that require user action (e.g., activity_voting),
        # avoid tight loops. The consensus agent will be triggered by user actions.
        if current_phase in ["activity_voting", "itinerary_approval"]:
            if status in ["active", "voting_in_progress", "pending"]:
                print(f"[orchestrator] ⏸️ {current_phase} awaiting user actions - orchestrator will pause")
                return False
        # Only trigger consensus if status is "active" (not "voting_in_progress" or "completed")
        result = status == "active"
        if result:
            print(f"[orchestrator] ✅ Consensus needed for phase: {current_phase}")
        elif status == "voting_in_progress":
            print(f"[orchestrator] ⏸️ Phase {current_phase} waiting for votes, skipping consensus")
        else:
            print(f"[orchestrator] ❌ Phase {current_phase} status '{status}' - no consensus needed")
        return result
    
    print(f"[orchestrator] Phase '{current_phase}' not found in phases dict")
    return False


def _needs_destination_research(state: AgentState) -> bool:
    """Check if destination research needs to be performed."""
    agent_data = state.get("agent_data", {}) or {}
    has_preferences = agent_data.get("preferences_summary") is not None
    has_catalog = agent_data.get("activity_catalog") is not None
    has_destination = bool(agent_data.get("destination"))
    
    # Don't do research if we're still in destination_decision phase (waiting for votes)
    phase_tracking = agent_data.get("phase_tracking", {})
    current_phase = phase_tracking.get("current_phase")
    if current_phase == "destination_decision":
        phases = phase_tracking.get("phases", {})
        dest_phase = phases.get("destination_decision", {})
        dest_status = dest_phase.get("status", "")
        if dest_status in ["active", "voting_in_progress"]:
            print(f"[orchestrator] Skipping destination research - destination_decision phase is {dest_status}")
            return False
    
    result = has_preferences and has_destination and not has_catalog
    if result:
        print(f"[orchestrator] Destination research needed for {agent_data.get('destination')}")
    return result


def _needs_itinerary_generation(state: AgentState) -> bool:
    """Check if itinerary generation needs to be performed."""
    agent_data = state.get("agent_data", {}) or {}
    has_catalog = agent_data.get("activity_catalog") is not None
    has_itinerary = agent_data.get("itinerary") is not None
    trip_duration_days = agent_data.get("trip_duration_days") or state.get("trip_duration_days")
    
    # Check if activity voting phase is completed
    phase_tracking = agent_data.get("phase_tracking")
    activity_voting_complete = False
    
    if phase_tracking:
        phases = phase_tracking.get("phases", {})
        activity_phase = phases.get("activity_voting", {})
        status = activity_phase.get("status", "pending")
        activity_voting_complete = status == "completed"
        
        # Log current activity voting status
        print(f"[orchestrator] Activity voting phase status: {status}")
        
        if status == "active":
            print(f"[orchestrator] Activity voting in progress - waiting for users to vote")
            return False
        elif status == "pending":
            print(f"[orchestrator] Activity voting not yet started - waiting for activities")
            return False
    else:
        # No phase_tracking means old trip without voting system
        print(f"[orchestrator] No phase_tracking found - this shouldn't happen for new trips")
        return False
    
    # Only generate itinerary if we have catalog, duration, no itinerary yet, AND activity voting is done
    result = has_catalog and bool(trip_duration_days) and not has_itinerary and activity_voting_complete
    
    if result:
        print(f"[orchestrator] ✅ Itinerary generation needed for {trip_duration_days} days")
    elif has_catalog and bool(trip_duration_days) and not has_itinerary:
        print(f"[orchestrator] ⏸️ Itinerary generation blocked - waiting for activity voting to complete")
    
    return result

def _is_waiting_for_user_action(state: AgentState) -> tuple[bool, str]:
    """
    Detect situations where the orchestrator should pause and wait
    for users instead of continuing (to avoid LLM fallback).
    """
    agent_data = state.get("agent_data", {}) or {}
    phase_tracking = agent_data.get("phase_tracking") or {}
    phases = phase_tracking.get("phases", {}) or {}
    current_phase = phase_tracking.get("current_phase")
    # When a current phase exists and is in a waiting status, pause
    if current_phase:
        status = (phases.get(current_phase) or {}).get("status", "")
        if status in ["voting_in_progress", "pending", "active"]:
            if current_phase == "destination_decision" and status == "voting_in_progress":
                return True, "Waiting for destination votes"
            if current_phase == "date_selection" and status == "voting_in_progress":
                return True, "Waiting for date votes"
            # Treat 'pending' as waiting as well because phase has been created but users haven't started
            if current_phase == "activity_voting" and status in ["pending", "active", "voting_in_progress"]:
                return True, "Waiting for activity votes"
            if current_phase == "itinerary_approval" and status in ["pending", "active", "voting_in_progress"]:
                return True, "Waiting for itinerary approvals"
    else:
        # If no current phase but activity voting exists and isn't completed yet, pause
        av_status = (phases.get("activity_voting") or {}).get("status")
        if av_status in ["pending", "active", "voting_in_progress"]:
            return True, "Waiting for activity voting to start/complete"
    return False, ""


def supervisor_agent(state: AgentState) -> AgentState:
    """Supervisor node: decides which agent to run next."""
    # Increment steps counter
    steps = state.get("steps", 0) + 1

    # Safety check: max iterations
    MAX_STEPS = 20
    if steps >= MAX_STEPS:
        return {
            "next_task": "end",
            "reason": f"Reached maximum steps ({MAX_STEPS})",
            "steps": steps,
            "done": True,
        }

    # Fast guardrail (deterministic suggestion)
    deterministic_suggestion: str | None = None

    if _needs_preference_processing(state):
        deterministic_suggestion = "preference_processor"
    elif _needs_consensus(state):
        deterministic_suggestion = "consensus_resolver"
    elif _needs_destination_research(state):
        deterministic_suggestion = "destination_researcher"
    elif _needs_itinerary_generation(state):
        deterministic_suggestion = "itinerary_planner"

    # Build LLM prompt with snapshot + registry
    registry_block = "\n".join([f"- {k}: {v['desc']}" for k, v in WORKERS.items()])
    trip_id = state.get("trip_id") or state.get("trip_id")
    agent_data = state.get("agent_data", {}) or {}
    snapshot = {
        "trip_id": trip_id,
        "goal": state.get("goal", ""),
        "destination": agent_data.get("destination", ""),
        "has_preferences_summary": bool(agent_data.get("preferences_summary")),
        "has_activity_catalog": bool(agent_data.get("activity_catalog")),
        "has_itinerary": bool(agent_data.get("itinerary")),
        "needs_preference_processing": _needs_preference_processing(state),
        "needs_consensus": _needs_consensus(state),
        "needs_destination_research": _needs_destination_research(state),
        "needs_itinerary_generation": _needs_itinerary_generation(state),
        "current_step": steps,
    }

    history_text = "\n".join(
        getattr(m, "content", "") for m in state.get("messages", []) if hasattr(m, "content")
    )

    user_prompt = f"""State snapshot:
{snapshot}

History:
{history_text}
"""

    # If there is no deterministic next task AND we are waiting for user action,
    # pause without calling the LLM. Do NOT pause if there is work to do
    # (e.g., destination_researcher should run before activity voting).
    if not deterministic_suggestion:
        waiting, waiting_reason = _is_waiting_for_user_action(state)
        if waiting:
            print(f"\n[SUPERVISOR - Step {steps}]")
            print(f"  Next task: end")
            print(f"  Reason: {waiting_reason}")
            print(f"  Deterministic suggestion: None (paused)")
            print(f"  State snapshot: {snapshot}")
            return {
                "next_task": "end",
                "reason": waiting_reason,
                "steps": steps,
                # Not done: we are pausing for user input
                "done": False,
            }

    # If LLM unavailable OR we have a clear deterministic path, use it directly
    if llm is None or deterministic_suggestion:
        next_task = deterministic_suggestion or "end"
        reason = (
            f"Deterministic routing: {deterministic_suggestion}"
            if deterministic_suggestion
            else "No more work needed; ending workflow"
        )
        print(f"\n[SUPERVISOR - Step {steps}]")
        print(f"  Next task: {next_task}")
        print(f"  Reason: {reason}")
        print(f"  Deterministic suggestion: {deterministic_suggestion}")
        print(f"  State snapshot: {snapshot}")
        return {
            "next_task": next_task,
            "reason": reason,
            "steps": steps,
            "done": next_task == "end",
        }

    # Only call LLM if no deterministic path found (rare edge cases)
    # This should rarely happen with proper deterministic routing
    print(f"[orchestrator] ⚠️ No deterministic path - using LLM fallback (rare case)")
    choice = llm.with_structured_output(SupervisorChoice).invoke(
        [
            {
                "role": "system",
                "content": SUPERVISOR_SYS.format(registry_block=registry_block),
            },
            {"role": "user", "content": user_prompt},
        ]
    )

    next_task = choice.next_task.strip()
    # Validate against registry
    if next_task not in WORKERS and next_task != "end":
        # Fallback to deterministic or end
        next_task = deterministic_suggestion or "end"

    # Log supervisor decision
    print(f"\n[SUPERVISOR - Step {steps}]")
    print(f"  Next task: {next_task}")
    print(
        f"  Reason: {choice.reason if next_task == choice.next_task else f'LLM proposed {choice.next_task}; coerced to {next_task}.'}"
    )
    if deterministic_suggestion:
        print(f"  Deterministic suggestion: {deterministic_suggestion}")
    print(f"  State snapshot: {snapshot}")

    return {
        "next_task": next_task,
        "reason": choice.reason
        if next_task == choice.next_task
        else f"LLM proposed {choice.next_task}; coerced to {next_task}.",
        "steps": steps,
        "done": next_task == "end",
    }


def agent_router(state: AgentState) -> str:
    """Route to the appropriate agent node based on next_task."""
    if state["next_task"] == "end":
        return "end"
    # Map registry key to node
    node = WORKERS[state["next_task"]]["node"]
    return node


# ---- Agent wrappers for proper state handling ----
async def preference_agent_wrapper(state: AgentState) -> AgentState:
    print("\n[AGENT] Running preference_agent...")
    result = await preference_agent.app.ainvoke(state)
    print("[AGENT] preference_agent completed.")
    return result


async def destination_research_agent_wrapper(state: AgentState) -> AgentState:
    print("\n[AGENT] Running destination_research_agent...")
    # Explicitly broadcast a starting status to guarantee UI updates
    try:
        from app.router.chat import broadcast_to_chat
        trip_id = state.get("trip_id")
        dest_name = (state.get("agent_data") or {}).get("destination") or "destination"
        if trip_id:
            await broadcast_to_chat(
                str(trip_id),
                {
                    "type": "agent_status",
                    "agent_name": "Destination Research Agent",
                    "status": "starting",
                    "step": f"Preparing to research {dest_name}",
                    "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
                },
            )
    except Exception as _broadcast_err:
        # Non-fatal - continue even if we can't broadcast early status
        print(f"[destination_research_agent_wrapper] Warning: failed to broadcast starting status: {_broadcast_err}")
    result = await destination_research_agent.app.ainvoke(state)
    print("[AGENT] destination_research_agent completed.")
    
    # Save activities to database so they appear in the UI
    agent_data = result.get("agent_data", {}) or {}
    activities = agent_data.get("activity_catalog", []) or []
    trip_id = result.get("trip_id")
    
    if activities and trip_id:
        try:
            from app.db.database import get_activities_collection
            from app.models.activity import Activity
            
            col = get_activities_collection()
            
            # Clear existing activities for this trip
            await col.delete_many({"trip_id": trip_id})
            
            # Convert activities to database documents
            docs = []
            for a in activities:
                try:
                    # Normalize to dict from either Pydantic model or plain dict
                    if hasattr(a, "model_dump"):
                        a_dict = a.model_dump()  # type: ignore[attr-defined]
                    elif isinstance(a, dict):
                        a_dict = dict(a)
                    else:
                        # Fallback: attempt attribute access
                        a_dict = {
                            "trip_id": getattr(a, "trip_id", None),
                            "name": getattr(a, "name", None),
                            "category": getattr(a, "category", None),
                            "rough_cost": getattr(a, "rough_cost", None),
                            "duration_min": getattr(a, "duration_min", None),
                            "lat": getattr(a, "lat", None),
                            "lng": getattr(a, "lng", None),
                            "tags": list(getattr(a, "tags", []) or []),
                            "fits": list(getattr(a, "fits", []) or []),
                            "score": getattr(a, "score", 0.0),
                            "rationale": getattr(a, "rationale", ""),
                            "photo_url": getattr(a, "photo_url", None),
                        }
                    doc = Activity(
                        trip_id=str(a_dict.get("trip_id") or trip_id),
                        name=str(a_dict.get("name", "")),
                        category=str(a_dict.get("category", "Other")),
                        rough_cost=a_dict.get("rough_cost"),
                        duration_min=a_dict.get("duration_min"),
                        lat=a_dict.get("lat"),
                        lng=a_dict.get("lng"),
                        tags=list(a_dict.get("tags") or []),
                        fits=list(a_dict.get("fits") or []),
                        score=float(a_dict.get("score") or 0.0),
                        rationale=str(a_dict.get("rationale") or ""),
                        photo_url=a_dict.get("photo_url"),
                    )
                    docs.append(doc.model_dump())
                except Exception as e:
                    print(f"[orchestrator] Skipping invalid activity: {e}")
            
            if docs:
                res = await col.insert_many(docs)
                print(f"[orchestrator] ✅ Saved {len(res.inserted_ids)} activities to database for trip {trip_id}")
                
                # Broadcast a guaranteed 'completed' status so UI reflects completion
                try:
                    from app.router.chat import broadcast_to_chat
                    await broadcast_to_chat(
                        str(trip_id),
                        {
                            "type": "agent_status",
                            "agent_name": "Destination Research Agent",
                            "status": "completed",
                            "step": f"Generated {len(res.inserted_ids)} activity suggestions",
                            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
                            "progress": {"current": 4, "total": 4},
                        },
                    )
                except Exception as _broadcast_err:
                    print(f"[orchestrator] Warning: failed to broadcast destination research completion: {_broadcast_err}")
                
                # Initialize activity_voting phase
                from app.db.database import get_database
                from bson import ObjectId
                from datetime import datetime
                
                try:
                    db = get_database()
                    trips = db.trips
                    
                    # Initialize phase tracking if not exists
                    trip_doc = await trips.find_one({"_id": ObjectId(trip_id)})
                    if trip_doc:
                        phase_tracking = trip_doc.get("phase_tracking", {})
                        phases = phase_tracking.get("phases", {})
                        
                        # Initialize activity_voting phase only if it doesn't exist yet
                        if "activity_voting" not in phases:
                            phases["activity_voting"] = {
                                "status": "pending",
                                "created_at": datetime.utcnow(),
                                "description": "Members vote on suggested activities"
                            }
                        
                        # Only update the activity_voting phase, DON'T change current_phase
                        # The current_phase should remain on destination/date consensus until those are resolved
                        # Only write if we actually created it to avoid overwriting an active phase
                        if "activity_voting" in phases and not trip_doc.get("phase_tracking", {}).get("phases", {}).get("activity_voting"):
                            await trips.update_one(
                                {"_id": ObjectId(trip_id)},
                                {
                                    "$set": {
                                        "phase_tracking.phases.activity_voting": phases["activity_voting"],
                                        "updated_at": datetime.utcnow()
                                    }
                                }
                            )
                        
                        # Update agent_data with phase_tracking but preserve current_phase
                        # Respect any phase_tracking already set by the agent (e.g., set to active)
                        if not agent_data.get("phase_tracking"):
                            agent_data["phase_tracking"] = {
                                "current_phase": phase_tracking.get("current_phase"),
                                "phases": phases
                            }
                            result["agent_data"] = agent_data
                        else:
                            # Merge in activity_voting phase if we added it and it's missing
                            ad_pt = agent_data.get("phase_tracking") or {}
                            ad_phases = ad_pt.get("phases") or {}
                            if "activity_voting" not in ad_phases and "activity_voting" in phases:
                                ad_phases["activity_voting"] = phases["activity_voting"]
                                ad_pt["phases"] = ad_phases
                                agent_data["phase_tracking"] = ad_pt
                                result["agent_data"] = agent_data
                        
                        print(f"[orchestrator] ✅ Initialized activity_voting phase (status: pending)")
                except Exception as e:
                    print(f"[orchestrator] ❌ Failed to initialize activity_voting phase: {e}")
            else:
                print(f"[orchestrator] ⚠️ No valid activities to save")
        except Exception as e:
            print(f"[orchestrator] ❌ Failed to save activities: {e}")
    
    return result


async def itinerary_agent_wrapper(state: AgentState) -> AgentState:
    print("\n[AGENT] Running itinerary_agent...")
    result = await itinerary_agent.app.ainvoke(state)
    print("[AGENT] itinerary_agent completed.")
    return result


async def consensus_agent_wrapper(state: AgentState) -> AgentState:
    print("\n[AGENT] Running consensus_agent...")
    result = await consensus_agent.run(state)
    
    # Check if consensus cleared phase_tracking (meaning it's done)
    agent_data = result.get("agent_data", {}) or {}
    
    # If consensus cleared phase_tracking, it means destination was resolved
    # Don't reload from DB - let orchestrator continue with resolved destination
    if agent_data.get("phase_tracking") is None:
        destination = agent_data.get("destination")
        if destination:
            print(f"[AGENT] ✅ Consensus resolved destination: {destination}")
            print(f"[AGENT] Orchestrator will now proceed to destination_research")
    else:
        # Consensus is waiting (voting_in_progress) - reload to get latest state
        trip_id = state.get("trip_id")
        if trip_id:
            from app.db.database import get_database
            from bson import ObjectId
            db = get_database()
            trips = db.trips
            
            try:
                trip = await trips.find_one({"_id": ObjectId(trip_id)})
            except:
                trip = await trips.find_one({"trip_code": trip_id.upper()})
            
            if trip:
                phase_tracking = trip.get("phase_tracking")
                if phase_tracking:
                    current_phase = phase_tracking.get("current_phase")
                    if current_phase:
                        status = phase_tracking.get("phases", {}).get(current_phase, {}).get("status")
                        print(f"[AGENT] Phase {current_phase} status: {status}")
                    agent_data["phase_tracking"] = phase_tracking
                    result["agent_data"] = agent_data
    
    print("[AGENT] consensus_agent completed.")
    return result


# ---- Build the top-level graph ----
graph = StateGraph(AgentState)
graph.add_node("supervisor_agent", supervisor_agent)
graph.add_node("preference_agent", preference_agent_wrapper)
graph.add_node("consensus_agent", consensus_agent_wrapper)
graph.add_node("destination_research_agent", destination_research_agent_wrapper)
graph.add_node("itinerary_agent", itinerary_agent_wrapper)

graph.set_entry_point("supervisor_agent")
graph.add_conditional_edges(
    "supervisor_agent",
    agent_router,
    {
        "preference_agent": "preference_agent",
        "consensus_agent": "consensus_agent",
        "destination_research_agent": "destination_research_agent",
        "itinerary_agent": "itinerary_agent",
        "end": END,
    },
)
graph.add_edge("preference_agent", "supervisor_agent")
graph.add_edge("consensus_agent", "supervisor_agent")
graph.add_edge("destination_research_agent", "supervisor_agent")
graph.add_edge("itinerary_agent", "supervisor_agent")

# Compile without checkpointer to avoid msgpack serialization issues
app = graph.compile()
config = {"recursion_limit": 50}


async def run_orchestrator_agent(initial_state: AgentState) -> AgentState:
    """
    Run the orchestrator with an initial state.

    Args:
        initial_state: Initial state containing trip_id, goal, etc.

    Returns:
        Final state after workflow completion
    """
    base: AgentState = {
        "messages": [],
        "trip_id": "",
        "agent_data": {},
        "agent_scratch": {},
        "steps": 0,
        "done": False,
        "next_task": "",
        "reason": "",
        "goal": "",
    }
    base.update(initial_state or {})

    # Support both trip_id and trip_id (backward compatibility)+
    if base.get("trip_id") and not base.get("trip_id"):
        base["trip_id"] = base["trip_id"]

    print(f"\n{'=' * 60}")
    print("Starting orchestrator")
    print(f"Trip ID: {base.get('trip_id', 'N/A')}")
    print(f"Goal: {base.get('goal', 'N/A')}")
    print(f"{'=' * 60}\n")

    result = await app.ainvoke(base, config=config)

    print(f"\n{'=' * 60}")
    print(f"Orchestrator completed after {result.get('steps', 0)} steps")
    print(f"Final status: {'SUCCESS' if result.get('done') else 'INCOMPLETE'}")
    print(f"Reason: {result.get('reason', 'N/A')}")
    print(f"{'=' * 60}\n")

    return result
