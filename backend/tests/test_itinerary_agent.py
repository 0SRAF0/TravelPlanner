import sys
import os
import json
from pathlib import Path
from typing import Dict, Any
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.runnables import RunnableLambda

# Allow importing from backend/app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.itinerary_agent import (
    ItineraryAgent,
    ItineraryGenerationInput,
    ItineraryOut,
    DayItinerary,
    ItineraryItem,
)
from app.agents.agent_state import AgentState


def print_section(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


@pytest.fixture
def mock_llm():
    """Fixture to mock the LLM for deterministic testing."""
    mock = MagicMock()

    # Create the expected ItineraryOut response
    expected_response = ItineraryOut(
        itinerary=[
            DayItinerary(
                day=1,
                date="2025-12-25",
                items=[
                    ItineraryItem(
                        activity_id="mock_act_1",
                        name="Breakfast at hotel",
                        start_time="09:00",
                        end_time="10:00",
                    ),
                    ItineraryItem(
                        activity_id="mock_act_2",
                        name="Visit local museum",
                        start_time="10:00",
                        end_time="12:00",
                    ),
                ],
            )
        ],
        insights=["Mock insight: Itinerary generated successfully."],
        warnings=[],
        metrics={"total_activities": 2, "average_items_per_day": 2},
        provenance=["mock_llm"],
    )

    # Mock the with_structured_output chain
    # When with_structured_output is called, it returns a runnable
    # Use RunnableLambda to create a proper Runnable that returns the expected response
    def mock_invoke(input_dict):
        return expected_response

    structured_mock = RunnableLambda(mock_invoke)
    mock.with_structured_output.return_value = structured_mock

    return mock


def _run_itinerary_agent_demo(mock_llm_instance: MagicMock) -> Dict[str, Any]:
    """Helper function to run the ItineraryAgent with a mock LLM."""
    # Patch ChatGoogleGenerativeAI where it's imported in itinerary_agent.py
    # and also patch the API key to ensure the agent initializes correctly.
    with (
        patch(
            "app.agents.itinerary_agent.ChatGoogleGenerativeAI",
            return_value=mock_llm_instance,
        ),
        # Patch the imported name inside itinerary_agent since it uses:
        # from app.core.config import GOOGLE_AI_API_KEY
        patch("app.agents.itinerary_agent.GOOGLE_AI_API_KEY", "mock_api_key"),
    ):
        agent = ItineraryAgent()

        trip_id = "test_trip_123"
        destination = "Paris, France"
        start_date = "2025-12-25"
        end_date = "2025-12-26"
        duration_days = 2

        # Example preferences summary (complete for testing)
        preferences_summary = {
            "trip_id": trip_id,
            "members": ["user_alice", "user_bob"],
            "aggregated_vibes": {"culture": 0.9, "food": 0.8},
            "budget_levels": ["3"],
            "conflicts": [],
            "ready_for_planning": True,
            "coverage": 1.0,
            "destination": destination,
            "start_date": start_date,
            "end_date": end_date,
            "duration_days": duration_days,
        }

        # Build the state as the orchestrator would right before invoking this agent
        input_state: AgentState = {
            "messages": [],
            "trip_id": trip_id,
            "agent_data": {
                "preferences_summary": preferences_summary,
                "destination": destination,
                "start_date": start_date,
                "end_date": end_date,
                "duration_days": duration_days,
                "activity_catalog": [
                    {
                        "activity_id": "act_001",
                        "name": "Louvre Museum",
                        "category": "Culture",
                    },
                    {
                        "activity_id": "act_002",
                        "name": "Eiffel Tower",
                        "category": "Culture",
                    },
                    {
                        "activity_id": "act_003",
                        "name": "Bistro Paul",
                        "category": "Food",
                    },
                ],
            },
        }

        print_section("INPUT TO ITINERARY AGENT")
        print(json.dumps(input_state, indent=2, default=str))

        # Run the agent
        return agent.run(dict(input_state))


def test_itinerary_agent_simple(mock_llm):
    """
    Simple smoke test for ItineraryAgent.
    Mimics the OrchestratorAgent passing aggregated preferences and activity catalog.
    """
    print_section("INITIALIZING ITINERARY AGENT")

    output_state = _run_itinerary_agent_demo(mock_llm)

    # Extract output
    agent_data_out = output_state.get("agent_data", {}) or {}

    itinerary = agent_data_out.get("itinerary")
    insights = agent_data_out.get("insights")
    warnings = agent_data_out.get("warnings")
    metrics = agent_data_out.get("metrics")

    print_section("OUTPUT FROM ITINERARY AGENT")
    print(
        json.dumps(
            {
                "itinerary": itinerary,
                "insights": insights,
                "warnings": warnings,
                "metrics": metrics,
            },
            indent=2,
            default=str,
        )
    )

    # Minimal sanity checks
    assert itinerary is not None
    assert isinstance(itinerary, list)
    assert len(itinerary) > 0
    assert metrics is not None
    assert metrics["total_activities"] == 2
    assert isinstance(insights, list)
    assert isinstance(warnings, list)

    # Verify LLM was called (through the structured output chain)
    mock_llm.with_structured_output.assert_called_once()


if __name__ == "__main__":
    print("\n" + "🗓️" * 40)
    print(" " * 16 + "ITINERARY AGENT TEST")
    print("🗓️" * 40)
    try:
        # Create a dummy mock LLM for standalone execution
        dummy_mock_llm = MagicMock()
        dummy_mock_llm.invoke.return_value = {
            "itinerary": [
                {
                    "day": 1,
                    "date": "2025-12-25",
                    "items": [
                        {"time": "09:00", "description": "Breakfast at hotel"},
                        {"time": "10:00", "description": "Visit local museum"},
                    ],
                }
            ],
            "metrics": {"total_activities": 2, "average_items_per_day": 2},
        }
        _ = _run_itinerary_agent_demo(dummy_mock_llm)
        print("\n✅ TEST COMPLETED")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
