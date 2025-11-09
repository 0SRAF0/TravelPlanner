# orchestrator_agent.py - Multi-agent orchestrator for travel planner
from typing import Dict, Literal, Optional
from pydantic.v1 import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import GOOGLE_AI_MODEL
from app.agents.agent_state import AgentState
from app.agents.preference_agent import PreferenceAgent

# --- Instantiate agents ---
preference_agent = PreferenceAgent()

# --- Worker registry: add new agents here later ---
WORKERS: Dict[str, Dict[str, str]] = {
    # key -> graph node name + description
    "preference_processor": {
        "node": "preference_agent",
        "desc": "Process and save user travel preferences (budget, vibes, deal breakers)"
    },
    # Future agents:
    # "itinerary_planner": {"node": "itinerary_agent", "desc": "Generate trip itinerary"},
    # "accommodation_finder": {"node": "accommodation_agent", "desc": "Find suitable accommodations"},
    # "activity_recommender": {"node": "activity_agent", "desc": "Recommend activities and attractions"},
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
1) If group_id exists and no preferences_summary → preference_processor (fetch and aggregate)
2) If preferences_summary exists and goal involves planning → itinerary_planner (future)
3) If all relevant items are done or goal accomplished → end

Return JSON only.
"""


def _needs_preference_processing(state: AgentState) -> bool:
    """Check if preferences need to be fetched and processed."""
    # Check if we have a group_id and haven't processed yet
    group_id = state.get("group_id") or state.get("trip_id")
    agent_data = state.get("agent_data", {}) or {}
    has_summary = agent_data.get("preferences_summary") is not None
    return bool(group_id) and not has_summary


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
    deterministic_suggestion: Optional[str] = None

    if _needs_preference_processing(state):
        deterministic_suggestion = "preference_processor"

    # Build LLM prompt with snapshot + registry
    registry_block = "\n".join([f"- {k}: {v['desc']}" for k, v in WORKERS.items()])
    group_id = state.get("group_id") or state.get("trip_id")
    agent_data = state.get("agent_data", {}) or {}
    snapshot = {
        "group_id": group_id,
        "user_id": state.get("user_id"),
        "goal": state.get("goal", ""),
        "has_preferences_summary": bool(agent_data.get("preferences_summary")),
        "needs_preference_processing": _needs_preference_processing(state),
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
        [{"role": "system", "content": SUPERVISOR_SYS.format(registry_block=registry_block)},
         {"role": "user", "content": user_prompt}]
    )

    next_task = choice.next_task.strip()
    # Validate against registry
    if next_task not in WORKERS and next_task != "end":
        # Fallback to deterministic or end
        next_task = deterministic_suggestion or "end"

    # Log supervisor decision
    print(f"\n[SUPERVISOR - Step {steps}]")
    print(f"  Next task: {next_task}")
    print(f"  Reason: {choice.reason if next_task == choice.next_task else f'LLM proposed {choice.next_task}; coerced to {next_task}.'}")
    if deterministic_suggestion:
        print(f"  Deterministic suggestion: {deterministic_suggestion}")
    print(f"  State snapshot: {snapshot}")

    return {
        "next_task": next_task,
        "reason": choice.reason if next_task == choice.next_task else f"LLM proposed {choice.next_task}; coerced to {next_task}.",
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
    print(f"[AGENT] preference_agent completed.")
    return result


# ---- Build the top-level graph ----
graph = StateGraph(AgentState)
graph.add_node("supervisor_agent", supervisor_agent)
graph.add_node("preference_agent", preference_agent_wrapper)

graph.set_entry_point("supervisor_agent")
graph.add_conditional_edges(
    "supervisor_agent",
    agent_router,
    {
        "preference_agent": "preference_agent",
        "end": END,
    },
)
graph.add_edge("preference_agent", "supervisor_agent")

checkpointer = MemorySaver()
app = graph.compile(checkpointer=checkpointer)
config = {
    "configurable": {"thread_id": "1"},
    "recursion_limit": 50
}


def run_orchestrator_agent(initial_state: AgentState) -> AgentState:
    """
    Run the orchestrator with an initial state.

    Args:
        initial_state: Initial state containing group_id, user_id, goal, etc.

    Returns:
        Final state after workflow completion
    """
    base: AgentState = {
        "messages": [],
        "group_id": "",
        "user_id": "",
        "agent_data": {},
        "agent_scratch": {},
        "steps": 0,
        "done": False,
        "next_task": "",
        "reason": "",
        "goal": ""
    }
    base.update(initial_state or {})

    # Support both group_id and trip_id (backward compatibility)
    if base.get("trip_id") and not base.get("group_id"):
        base["group_id"] = base["trip_id"]

    print(f"\n{'=' * 60}")
    print(f"Starting orchestrator")
    print(f"Group ID: {base.get('group_id', 'N/A')}")
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


# --- Demo / Test ---
if __name__ == "__main__":
    initial_state: AgentState = {
        "messages": [HumanMessage(content="I want to plan a trip to Japan")],
        "group_id": "group_123",
        "user_id": "user_456",
        "goal": "Fetch and aggregate group preferences for Japan trip"
    }

    result = run_orchestrator_agent(initial_state)

    # Display results
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)

    agent_data = result.get('agent_data', {})
    summary = agent_data.get('preferences_summary')
    if summary:
        print(f"\nGroup: {summary.get('group_id')}")
        print(f"Members: {summary.get('members')}")
        print(f"Ready for planning: {summary.get('ready_for_planning')}")
        print(f"Aggregated vibes: {summary.get('aggregated_vibes')}")
        print(f"Budget levels: {summary.get('budget_levels')}")
        print(f"Conflicts: {summary.get('conflicts')}")
        print(f"Coverage: {summary.get('coverage'):.0%}")

    print("\n" + "=" * 60)

