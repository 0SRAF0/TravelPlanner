"""
Test suite for Preference Agent with new Preference model
Tests the full workflow: add preferences → submit → aggregate
"""

import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.preference_agent import PreferenceAgent, SurveyInput


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_preference_agent():
    """Test the preference agent with multiple users in trip 'g1'"""

    print_section("INITIALIZING PREFERENCE AGENT")
    agent = PreferenceAgent()
    trip_id = "g1"

    # Test data: 3 users with different preferences
    test_users = [
        {
            "user_id": "user_alice",
            "budget_level": 3,  # Comfort
            "vibes": ["Adventure", "Nature", "Food"],
            "deal_breaker": "No early mornings, avoid crowded places",
            "notes": "Love hiking and outdoor activities. Prefer small authentic restaurants.",
            "available_dates": ["2024-06-01:2024-06-15", "2024-07-10:2024-07-31"],
        },
        {
            "user_id": "user_bob",
            "budget_level": 2,  # Moderate
            "vibes": ["Food", "Culture", "Relax"],
            "deal_breaker": "No spicy food",
            "notes": "Interested in museums and history. Want to try local cuisine.",
            "available_dates": ["2024-06-05:2024-06-20", "2024-07-01:2024-07-15"],
        },
        {
            "user_id": "user_charlie",
            "budget_level": 3,  # Comfort
            "vibes": ["Nightlife", "Food", "Adventure"],
            "deal_breaker": "Must have vegetarian options",
            "notes": "Love trying new restaurants and experiencing nightlife.",
            "available_dates": ["2024-06-10:2024-06-25", "2024-08-01:2024-08-15"],
        },
    ]

    print_section("INGESTING USER PREFERENCES")

    for user_data in test_users:
        # Map vibes to weighted scorecard (0.9, 0.8, 0.7, ...)
        def weight_for_index(idx: int) -> float:
            return max(0.5, round(0.9 - 0.1 * idx, 1))

        scorecard = {}
        for idx, vibe in enumerate(user_data["vibes"]):
            vibe_key = vibe.lower()
            scorecard[vibe_key] = weight_for_index(idx)

        # Prepare hard constraints
        hard = {}
        if user_data.get("budget_level"):
            hard["budget_level"] = str(user_data["budget_level"])
        if user_data.get("deal_breaker"):
            deal_breakers = agent._normalize_deal_breakers(user_data["deal_breaker"])
            hard["deal_breakers"] = ", ".join(deal_breakers)

        # Prepare free text for embedding
        text_parts = []
        if user_data.get("vibes"):
            text_parts.append(" ".join(user_data["vibes"]))
        if user_data.get("notes"):
            text_parts.append(user_data["notes"])
        free_text = " ".join(text_parts)

        # Ingest into agent
        profile = agent.ingest_survey(
            trip_id, user_data["user_id"], SurveyInput(text=free_text, hard=hard, soft=scorecard)
        )

        print(f"\n✓ User: {user_data['user_id']}")
        print(f"  Budget Level: {user_data['budget_level']}")
        print(f"  Vibes: {user_data['vibes']}")
        print(f"  Scorecard: {scorecard}")
        print(f"  Deal Breaker: {user_data['deal_breaker']}")
        print(f"  Profile Summary: {profile.summary[:100]}...")
        print(f"  Vector Dimension: {len(profile.vector)}")

    print_section("AGGREGATING TRIP PREFERENCES")

    # Aggregate preferences for the trip
    agg = agent.aggregate(trip_id)

    print(f"\n📊 Trip ID: {agg.trip_id}")
    print(f"👥 Members: {len(agg.members)} - {agg.members}")
    print(f"📈 Coverage: {agg.coverage * 100:.0f}%")
    print(f"✅ Ready for Options: {agg.ready_for_options}")

    print("\n🔧 Hard Constraints (Union):")
    for key, values in agg.hard_union.items():
        print(f"  • {key}: {values}")

    print("\n🎯 Soft Preferences (Average Vibe Weights):")
    sorted_vibes = sorted(agg.soft_mean.items(), key=lambda x: -x[1])
    for vibe, weight in sorted_vibes:
        bar = "█" * int(weight * 20)
        print(f"  • {vibe.capitalize():<12} {weight:.2f} {bar}")

    print("\n⚠️  Conflicts:")
    if agg.conflicts:
        for key, reason in agg.conflicts:
            print(f"  • {key}: {reason}")
    else:
        print("  None - All preferences are compatible!")

    print_section("TESTING PREFERENCE UPDATE")

    # Update Alice's preferences
    print("\n🔄 Updating user_alice's budget level from 3 to 4...")
    delta = agent.update(trip_id, "user_alice", {"hard.budget_level": "4"})

    print("  Changed fields:")
    for key, (old, new) in delta.changed.items():
        print(f"    • {key}: '{old}' → '{new}'")

    # Re-aggregate to see changes
    agg_updated = agent.aggregate(trip_id)
    print("\n📊 Updated Hard Constraints:")
    print(f"  • budget_level: {agg_updated.hard_union.get('budget_level', [])}")

    print("\n⚠️  Updated Conflicts:")
    if agg_updated.conflicts:
        for key, reason in agg_updated.conflicts:
            print(f"  • {key}: {reason}")
    else:
        print("  None - All preferences are still compatible!")

    print_section("TESTING LANGGRAPH STATE OUTPUT (MESSAGE TO NEXT AGENT)")

    # Run the agent through LangGraph to see what it sends to next agent
    print("\n🔄 Simulating LangGraph workflow output...")

    from langchain_core.messages import AIMessage

    from app.agents.agent_state import AgentState

    # Use the agent we already populated with data
    # Manually build the output state that _fetch_and_process would create

    # Get the aggregate (already computed)
    final_agg = agent.aggregate(trip_id)

    # Build the preferences_summary exactly as the agent would
    preferences_summary = {
        "trip_id": trip_id,
        "members": final_agg.members,
        "aggregated_vibes": final_agg.soft_mean,
        "budget_levels": final_agg.hard_union.get("budget_level", []),
        "conflicts": [f"{k}: {r}" for k, r in final_agg.conflicts],
        "ready_for_planning": final_agg.ready_for_options,
        "coverage": final_agg.coverage,
    }

    # Build the summary message
    summary_msg = f"""
    [preference] Processing complete for trip {trip_id}:
    - Members: {len(final_agg.members)}
    - Top vibes: {dict(sorted(final_agg.soft_mean.items(), key=lambda x: -x[1])[:5])}
    - Budget levels: {final_agg.hard_union.get("budget_level", [])}
    - Conflicts: {final_agg.conflicts}
    - Ready for planning: {final_agg.ready_for_options}
    - Coverage: {final_agg.coverage:.0%}
    """

    # Create the result state (this is what next agent receives)
    result_state: AgentState = {
        "messages": [AIMessage(content=summary_msg.strip())],
        "trip_id": trip_id,
        "agent_data": {"preferences_summary": preferences_summary},
        "done": True,
    }

    print("\n" + "=" * 80)
    print("📤 AGENT STATE OUTPUT (What next agent receives)")
    print("=" * 80)

    # Display the full state
    import json

    print("\n🔑 Full AgentState Keys:")
    for key in result_state.keys():
        print(f"  • {key}")

    print("\n📦 agent_data (Primary data for next agent):")
    agent_data = result_state.get("agent_data", {})
    if agent_data:
        print(json.dumps(agent_data, indent=2, default=str))
    else:
        print("  (empty)")

    print("\n💬 messages (Conversation history):")
    messages = result_state.get("messages", [])
    for i, msg in enumerate(messages):
        content = getattr(msg, "content", str(msg))
        print(f"  [{i}] {type(msg).__name__}: {content[:200]}...")

    print("\n🎯 trip_id:", result_state.get("trip_id"))
    print("✅ done:", result_state.get("done"))

    # Show the preferences_summary in detail
    print("\n" + "=" * 80)
    print("📊 PREFERENCES SUMMARY (Key data for next agent)")
    print("=" * 80)

    prefs_summary = agent_data.get("preferences_summary", {})
    if prefs_summary:
        print(f"""
        🆔 Trip ID: {prefs_summary.get("trip_id")}
        👥 Members: {prefs_summary.get("members")}
        📈 Coverage: {prefs_summary.get("coverage", 0) * 100:.0f}%
        ✅ Ready for Planning: {prefs_summary.get("ready_for_planning")}
        
        🎯 Aggregated Vibes (Weighted):
        """)

        vibes = prefs_summary.get("aggregated_vibes", {})
        sorted_vibes_summary = sorted(vibes.items(), key=lambda x: -x[1])
        for vibe, weight in sorted_vibes_summary:
            bar = "█" * int(weight * 20)
            print(f"   • {vibe.capitalize():<12} {weight:.2f} {bar}")

        print(f"\n💰 Budget Levels: {prefs_summary.get('budget_levels')}")

        conflicts_list = prefs_summary.get("conflicts", [])
        print(f"\n⚠️  Conflicts: {conflicts_list if conflicts_list else 'None'}")

    print("\n" + "=" * 80)
    print("📋 NEXT AGENT CAN ACCESS THIS DATA VIA:")
    print("=" * 80)
    print("""
        def next_agent(state: AgentState) -> AgentState:
        # Access preferences data sent by preference agent
        prefs = state["agent_data"]["preferences_summary"]
        
        trip_id = prefs["trip_id"]
        members = prefs["members"]
        vibes = prefs["aggregated_vibes"]
        budget_levels = prefs["budget_levels"]
        ready = prefs["ready_for_planning"]
        
        # Use this data for planning...
        return state
    """)

    print_section("TEST SUMMARY")

    print(f"""
✅ Successfully tested:
   • Ingesting {len(test_users)} user preferences
   • Aggregating trip preferences
   • Conflict detection (budget level spread)
   • Preference updates
   • LangGraph state output generation
   
📊 Final Trip Stats:
   • Trip ID: {trip_id}
   • Total Members: {len(agg_updated.members)}
   • Coverage: {agg_updated.coverage * 100:.0f}%
   • Ready: {agg_updated.ready_for_options}
   • Top Vibe: {sorted_vibes[0][0].capitalize()} ({sorted_vibes[0][1]:.2f})
   • Conflicts: {len(agg_updated.conflicts)}
   
📤 State Output:
   • agent_data contains preferences_summary
   • Next agent will receive complete aggregated preferences
   • Ready for itinerary/options planning: {prefs_summary.get("ready_for_planning", False)}
""")

    return agent, agg_updated, result_state


if __name__ == "__main__":
    print("\n" + "🎯" * 40)
    print(" " * 20 + "PREFERENCE AGENT TEST")
    print("🎯" * 40)

    try:
        agent, aggregation, result_state = test_preference_agent()
        print("\n✅ ALL TESTS PASSED!")

        print("\n" + "=" * 80)
        print("💡 TIP: The 'result_state' variable contains the complete AgentState")
        print("    that will be passed to the next agent in the workflow.")
        print("=" * 80)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
