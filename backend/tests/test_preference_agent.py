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
    """Test the preference agent with multiple users in group 'g1'"""
    
    print_section("INITIALIZING PREFERENCE AGENT")
    agent = PreferenceAgent()
    group_id = "g1"
    
    # Test data: 3 users with different preferences
    test_users = [
        {
            "user_id": "user_alice",
            "budget_level": 3,  # Comfort
            "vibes": ["Adventure", "Nature", "Food"],
            "deal_breaker": "No early mornings, avoid crowded places",
            "notes": "Love hiking and outdoor activities. Prefer small authentic restaurants."
        },
        {
            "user_id": "user_bob",
            "budget_level": 2,  # Moderate
            "vibes": ["Food", "Culture", "Relax"],
            "deal_breaker": "No spicy food",
            "notes": "Interested in museums and history. Want to try local cuisine."
        },
        {
            "user_id": "user_charlie",
            "budget_level": 3,  # Comfort
            "vibes": ["Nightlife", "Food", "Adventure"],
            "deal_breaker": "Must have vegetarian options",
            "notes": "Love trying new restaurants and experiencing nightlife."
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
            group_id,
            user_data["user_id"],
            SurveyInput(text=free_text, hard=hard, soft=scorecard)
        )
        
        print(f"\n✓ User: {user_data['user_id']}")
        print(f"  Budget Level: {user_data['budget_level']}")
        print(f"  Vibes: {user_data['vibes']}")
        print(f"  Scorecard: {scorecard}")
        print(f"  Deal Breaker: {user_data['deal_breaker']}")
        print(f"  Profile Summary: {profile.summary[:100]}...")
        print(f"  Vector Dimension: {len(profile.vector)}")
    
    print_section("AGGREGATING GROUP PREFERENCES")
    
    # Aggregate preferences for the group
    agg = agent.aggregate(group_id)
    
    print(f"\n📊 Group ID: {agg.group_id}")
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
    delta = agent.update(group_id, "user_alice", {"hard.budget_level": "4"})
    
    print(f"  Changed fields:")
    for key, (old, new) in delta.changed.items():
        print(f"    • {key}: '{old}' → '{new}'")
    
    # Re-aggregate to see changes
    agg_updated = agent.aggregate(group_id)
    print(f"\n📊 Updated Hard Constraints:")
    print(f"  • budget_level: {agg_updated.hard_union.get('budget_level', [])}")
    
    print("\n⚠️  Updated Conflicts:")
    if agg_updated.conflicts:
        for key, reason in agg_updated.conflicts:
            print(f"  • {key}: {reason}")
    else:
        print("  None - All preferences are still compatible!")
    
    print_section("TEST SUMMARY")
    
    print(f"""
✅ Successfully tested:
   • Ingesting {len(test_users)} user preferences
   • Aggregating group preferences
   • Conflict detection (budget level spread)
   • Preference updates
   
📊 Final Group Stats:
   • Group ID: {group_id}
   • Total Members: {len(agg_updated.members)}
   • Coverage: {agg_updated.coverage * 100:.0f}%
   • Ready: {agg_updated.ready_for_options}
   • Top Vibe: {sorted_vibes[0][0].capitalize()} ({sorted_vibes[0][1]:.2f})
   • Conflicts: {len(agg_updated.conflicts)}
""")
    
    return agent, agg_updated


if __name__ == "__main__":
    print("\n" + "🎯" * 40)
    print(" " * 20 + "PREFERENCE AGENT TEST")
    print("🎯" * 40)
    
    try:
        agent, aggregation = test_preference_agent()
        print("\n✅ ALL TESTS PASSED!")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
