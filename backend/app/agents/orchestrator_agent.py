# orchestrator_agent.py - Multi-agent orchestrator for travel planner
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic.v1 import BaseModel, Field

from app.agents.agent_state import AgentState
from app.agents.destination_research_agent import DestinationResearchAgent
from app.agents.itinerary_agent import ItineraryAgent
from app.agents.preference_agent import PreferenceAgent
from app.core.config import GOOGLE_AI_MODEL

# --- Instantiate agents ---
preference_agent = PreferenceAgent()
destination_research_agent = DestinationResearchAgent()
itinerary_agent = ItineraryAgent()

# --- Worker registry: add new agents here later ---
WORKERS: dict[str, dict[str, str]] = {
    # key -> graph node name + description
    "preference_processor": {
        "node": "preference_agent",
        "desc": "Process and save user travel preferences (budget, vibes, deal breakers)",
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
llm = ChatGoogleGenerativeAI(model=GOOGLE_AI_MODEL)


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
2) If preferences_summary exists, destination provided, and no activity_catalog → destination_researcher
3) If activity_catalog exists, trip_duration_days is set, and no itinerary → itinerary_planner
4) If all relevant items are done or goal accomplished → end

Return JSON only.
"""


def _needs_preference_processing(state: AgentState) -> bool:
    """Check if preferences need to be fetched and processed."""
    # Check if we have a trip_id and haven't processed yet
    trip_id = state.get("trip_id")
    agent_data = state.get("agent_data", {}) or {}
    has_summary = agent_data.get("preferences_summary") is not None
    return bool(trip_id) and not has_summary


def _needs_destination_research(state: AgentState) -> bool:
    """Check if destination research needs to be performed."""
    agent_data = state.get("agent_data", {}) or {}
    has_preferences = agent_data.get("preferences_summary") is not None
    has_catalog = agent_data.get("activity_catalog") is not None
    has_destination = bool(agent_data.get("destination"))
    return has_preferences and has_destination and not has_catalog


def _needs_itinerary_generation(state: AgentState) -> bool:
    """Check if itinerary generation needs to be performed."""
    agent_data = state.get("agent_data", {}) or {}
    has_catalog = agent_data.get("activity_catalog") is not None
    has_itinerary = agent_data.get("itinerary") is not None
    trip_duration_days = agent_data.get("trip_duration_days") or state.get("trip_duration_days")
    return has_catalog and bool(trip_duration_days) and not has_itinerary


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
        "user_id": state.get("user_id"),
        "goal": state.get("goal", ""),
        "destination": agent_data.get("destination", ""),
        "has_preferences_summary": bool(agent_data.get("preferences_summary")),
        "has_activity_catalog": bool(agent_data.get("activity_catalog")),
        "has_itinerary": bool(agent_data.get("itinerary")),
        "needs_preference_processing": _needs_preference_processing(state),
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
def preference_agent_wrapper(state: AgentState) -> AgentState:
    print("\n[AGENT] Running preference_agent...")
    result = preference_agent.app.invoke(state)
    print("[AGENT] preference_agent completed.")
    return result


def destination_research_agent_wrapper(state: AgentState) -> AgentState:
    print("\n[AGENT] Running destination_research_agent...")
    result = destination_research_agent.app.invoke(state)
    print("[AGENT] destination_research_agent completed.")
    return result


def itinerary_agent_wrapper(state: AgentState) -> AgentState:
    print("\n[AGENT] Running itinerary_agent...")
    result = itinerary_agent.app.invoke(state)
    print("[AGENT] itinerary_agent completed.")
    return result


# ---- Build the top-level graph ----
graph = StateGraph(AgentState)
graph.add_node("supervisor_agent", supervisor_agent)
graph.add_node("preference_agent", preference_agent_wrapper)
graph.add_node("destination_research_agent", destination_research_agent_wrapper)
graph.add_node("itinerary_agent", itinerary_agent_wrapper)

graph.set_entry_point("supervisor_agent")
graph.add_conditional_edges(
    "supervisor_agent",
    agent_router,
    {
        "preference_agent": "preference_agent",
        "destination_research_agent": "destination_research_agent",
        "itinerary_planner": "itinerary_agent",
        "end": END,
    },
)
graph.add_edge("preference_agent", "supervisor_agent")
graph.add_edge("destination_research_agent", "supervisor_agent")
graph.add_edge("itinerary_agent", "supervisor_agent")

checkpointer = MemorySaver()
app = graph.compile(checkpointer=checkpointer)
config = {"configurable": {"thread_id": "1"}, "recursion_limit": 50}


def run_orchestrator_agent(initial_state: AgentState) -> AgentState:
    """
    Run the orchestrator with an initial state.

    Args:
        initial_state: Initial state containing trip_id, user_id, goal, etc.

    Returns:
        Final state after workflow completion
    """
    base: AgentState = {
        "messages": [],
        "trip_id": "",
        "user_id": "",
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
    print(f"User ID: {base.get('user_id', 'N/A')}")
    print(f"Goal: {base.get('goal', 'N/A')}")
    print(f"{'=' * 60}\n")

    result = app.invoke(base, config=config)

    print(f"\n{'=' * 60}")
    print(f"Orchestrator completed after {result.get('steps', 0)} steps")
    print(f"Final status: {'SUCCESS' if result.get('done') else 'INCOMPLETE'}")
    print(f"Reason: {result.get('reason', 'N/A')}")
    print(f"{'=' * 60}\n")

    return result
