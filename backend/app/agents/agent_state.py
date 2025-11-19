# agent_state.py - Generic multi-agent state (reusable across projects)
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """
    Generic state schema for multi-agent LangGraph applications.
    All agents share and update this state during execution.

    Core fields:
    - messages: Accumulated conversation history
    - trip_id: Primary identifier for trip
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

    Note:
    - Task-specific inputs (e.g., destination, hints) should live under
      agent_data (e.g., agent_data["destination"], agent_data["hints"]) or
      be passed via the calling context, not as top-level fields here.
    """

    # ========== Core Communication Fields ==========
    messages: Annotated[list, add_messages]

    # ========== Identifiers ==========
    trip_id: str  # trip_id

    # ========== Workflow Control ==========
    next_task: str  # Orchestrator routing
    last_task: str  # Previous agent executed
    reason: str  # Explanation for routing/state changes
    done: bool  # Workflow completion flag
    steps: int  # Iteration counter
    goal: str  # High-level objective

    # ========== Generic Storage (ALL agents use these) ==========
    agent_data: dict[str, Any]  # All agent outputs
    agent_scratch: dict[str, Any]  # All agent working memory
    
    # ========== WebSocket Broadcast Callback ==========
    broadcast_callback: Any  # Optional async callback for status updates
