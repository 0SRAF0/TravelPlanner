# agent_state.py - Generic multi-agent state (reusable across projects)
from typing import TypedDict, Annotated, Dict, Any
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """
    Generic state schema for multi-agent LangGraph applications.
    All agents share and update this state during execution.

    Core fields:
    - messages: Accumulated conversation history
    - group_id/trip_id: Primary identifier for group/trip
    - user_id: Current user identifier
    - goal: What the workflow is trying to accomplish
    - next_task: Routing decision for which agent to run next
    - done: Whether the workflow is complete

    Generic storage:
    - agent_data: Generic dict for ANY agent's output data
      Examples:
      - agent_data["preferences_summary"] = {...}  # PreferenceAgent
      - agent_data["itinerary"] = {...}            # ItineraryAgent
      - agent_data["recommendations"] = [...]      # RecommendationAgent

    - agent_scratch: Generic dict for ANY agent's working memory
      Examples:
      - agent_scratch["preference_processing"] = {...}
      - agent_scratch["itinerary_drafts"] = [...]

    This allows unlimited agents to coexist without state conflicts.
    """
    # ========== Core Communication Fields ==========
    messages: Annotated[list, add_messages]

    # ========== Identifiers ==========
    group_id: str  # Primary: group/trip identifier
    trip_id: str  # Alias for group_id (backward compatibility)

    # ========== Workflow Control ==========
    next_task: str  # Orchestrator routing
    last_task: str  # Previous agent executed
    reason: str  # Explanation for routing/state changes
    done: bool  # Workflow completion flag
    steps: int  # Iteration counter
    goal: str  # High-level objective

    # ========== Generic Storage (ALL agents use these) ==========
    agent_data: Dict[str, Any]  # All agent outputs
    agent_scratch: Dict[str, Any]  # All agent working memory
