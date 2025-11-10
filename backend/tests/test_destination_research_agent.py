import sys
import os
import json
from pathlib import Path
from typing import Dict, Any
import pytest

# Allow importing from backend/app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.destination_research_agent import DestinationResearchAgent
from app.agents.agent_state import AgentState


def print_section(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def _run_demo() -> Dict[str, Any]:

    agent = DestinationResearchAgent()

    trip_id = "g1"
    destination = "San Jose, CA, United State"

    # What the PreferenceAgent would pass forward
    preferences_summary = {
        "trip_id": trip_id,
        "members": ["user_alice", "user_bob", "user_charlie"],
        "aggregated_vibes": {
            "adventure": 0.9,
            "food": 0.85,
            "culture": 0.7,
            "relax": 0.6,
            "nightlife": 0.5,
            "nature": 0.65,
        },
        "budget_levels": ["3", "2", "3"],
        "conflicts": [],
        "ready_for_planning": True,
        "coverage": 1.0,
    }

    # Optional hints that could be provided by UI/orchestrator
    hints: Dict[str, Any] = {
        "radius_km": 10,
        "max_items": 10,
        "preferred_categories": ["Food", "Culture"],
    }

    # Build the state as the orchestrator would right before invoking this agent
    input_state: AgentState = {
        "messages": [],
        "trip_id": trip_id,
		"agent_data": {
			"preferences_summary": preferences_summary,
			"destination": destination,
			"hints": hints,
		},
    }

    print_section("INPUT TO DESTINATION RESEARCH AGENT (from PreferenceAgent)")
    print(
        json.dumps(
            {
                "preferences_summary": preferences_summary,
                "destination": destination,
                "hints": hints,
            },
            indent=2,
            default=str,
        )
    )

    # Run the agent
    return agent.run(dict(input_state))

def test_destination_research_agent_simple():
    """
    Simple smoke test for DestinationResearchAgent.
    Mimics the PreferenceAgent passing aggregated preferences to this agent.
    Prints the input (what comes from PreferenceAgent) and the output catalog.
    """
    print_section("INITIALIZING DESTINATION RESEARCH AGENT")

    output_state = _run_demo()

    # Extract output
    agent_data_out = output_state.get("agent_data", {}) or {}
    catalog = agent_data_out.get("activity_catalog", []) or []
    insights = agent_data_out.get("insights", []) or []
    warnings = agent_data_out.get("warnings", []) or []
    metrics = agent_data_out.get("metrics", {}) or {}
    provenance = agent_data_out.get("provenance", []) or []

    print_section("OUTPUT FROM DESTINATION RESEARCH AGENT")
	destination = (output_state.get("agent_data", {}) or {}).get("destination", "Unknown")
    print(f"Destination: {destination}")
    print(f"Activities returned: {len(catalog)}")

    if catalog:
        print("\n📋 ALL ACTIVITIES (Full JSON):")
        print(json.dumps(catalog, indent=2, default=str))

    print("\n💡 Insights:")
    for s in insights:
        print(f"  - {s}")

    print("\n⚠️  Warnings:")
    if warnings:
        for w in warnings:
            print(f"  - {w}")
    else:
        print("  None")

    print("\n📊 Metrics:")
    print(json.dumps(metrics, indent=2, default=str))

    print("\n🔍 Provenance:")
    print(provenance)

    # Minimal sanity checks so the test suite can pass regardless of LLM availability
    assert "activity_catalog" in agent_data_out
    assert "insights" in agent_data_out
    assert "warnings" in agent_data_out
    assert "metrics" in agent_data_out
    assert isinstance(catalog, list)

if __name__ == "__main__":
    print("\n" + "🧭" * 40)
    print(" " * 16 + "DESTINATION RESEARCH AGENT TEST")
    print("🧭" * 40)
    try:
        _ = _run_demo()
        print("\n✅ TEST COMPLETED")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


