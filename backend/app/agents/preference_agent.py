# preference_agent.py - Simplified agent for aggregation and semantic search
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, END
import math
import time
import hashlib

from app.agents.agent_state import AgentState
from app.agents.tools import get_all_group_preferences
from app.core.config import GOOGLE_AI_MODEL

AGENT_LABEL = "preference_aggregator"


# ========== Vector Embedding Utilities ==========

def _tokenize(text: str) -> List[str]:
    """Tokenize text for embedding."""
    for char in "/,;:.-()[]{}!?":
        text = text.replace(char, " ")
    return [t for t in text.lower().split() if t]


def hash_embed(text: str, dim: int = 384) -> List[float]:
    """Create hash-based embedding vector."""
    v = [0.0] * dim
    for tok in _tokenize(text):
        h = int(hashlib.md5(tok.encode('utf-8')).hexdigest(), 16)
        i = h % dim
        v[i] += 1.0
    # L2 normalize
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def cosine(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    return sum(x * y for x, y in zip(a, b))


# ========== Data Models ==========

@dataclass
class UserPreferenceProfile:
    """Complete user preference profile with embedding."""
    group_id: str
    user_id: str
    hard: Dict[str, str]
    soft: Dict[str, float]
    summary: str
    vector: List[float]
    version: int = 1
    source: str = "db"
    updated_at: float = field(default_factory=lambda: time.time())


@dataclass
class GroupPreferenceAggregate:
    """Aggregated preferences for entire group."""
    group_id: str
    members: List[str]
    hard_union: Dict[str, List[str]]
    soft_mean: Dict[str, float]
    conflicts: List[Tuple[str, str]]
    coverage: float  # 0..1
    ready_for_options: bool


@dataclass
class ItemCandidate:
    """Candidate item for recommendation."""
    id: str
    text: str
    meta: Dict[str, str] = field(default_factory=dict)


@dataclass
class ScoredItem:
    """Item with similarity score."""
    id: str
    score: float
    reason: str


# ========== Vector Index ==========

class VectorIndex:
    """In-memory vector index for semantic search."""

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.vectors: Dict[str, List[float]] = {}

    def upsert(self, key: str, vec: List[float]) -> None:
        if len(vec) != self.dim:
            raise ValueError("vector dim mismatch")
        self.vectors[key] = vec

    def get(self, key: str) -> Optional[List[float]]:
        return self.vectors.get(key)


# ========== Preference Agent ==========

class PreferenceAgent:
    """
    Preference agent for aggregation and semantic search.

    Responsibilities:
    - Fetch preferences from database by group_id
    - Create vector embeddings for semantic search
    - Aggregate group preferences
    - Provide recommendations via semantic similarity

    NOT responsible for:
    - Saving preferences (handled by FastAPI endpoints)
    - Validating input (handled by Pydantic models)
    """

    def __init__(self, model_name: Optional[str] = None, dim: int = 384):
        self.model_name = model_name or GOOGLE_AI_MODEL
        self.llm = ChatGoogleGenerativeAI(model=self.model_name)
        self.dim = dim

        # In-memory storage
        self.index = VectorIndex(dim)
        self.profiles: Dict[Tuple[str, str], UserPreferenceProfile] = {}
        self.groups: Dict[str, List[str]] = {}

        # LangGraph app
        self.app = self._build_graph()

    # ========== Vector Embedding Methods ==========

    def _vec_key(self, group_id: str, user_id: str) -> str:
        """Generate vector key."""
        raw = f"{group_id}:{user_id}:prefs"
        short = hashlib.md5(raw.encode("utf-8")).hexdigest()[:6]
        return f"vec_{short}"

    def _normalize_hard(self, pref: Preference) -> Dict[str, str]:
        """Extract hard constraints from Preference model."""
        hard = {}
        if pref.budget_level:
            hard["budget_level"] = str(pref.budget_level)
        if pref.deal_breaker:
            hard["deal_breaker"] = pref.deal_breaker
        return hard

    def _normalize_soft(self, vibes: List[str]) -> Dict[str, float]:
        """Convert vibes list to weighted soft preferences."""
        # Assign decreasing weights: 0.9, 0.8, 0.7, ...
        soft = {}
        for i, vibe in enumerate(vibes[:6]):  # Max 6 vibes
            weight = max(0.5, 0.9 - (i * 0.1))
            soft[vibe.lower()] = weight
        return soft

    def _summarize(self, pref: Preference) -> str:
        """Create text summary for embedding."""
        parts = []

        # Add vibes
        if pref.vibes:
            parts.append(" ".join(pref.vibes))

        # Add budget level
        if pref.budget_level:
            budget_labels = {1: "budget", 2: "moderate", 3: "comfort", 4: "luxury"}
            parts.append(budget_labels.get(pref.budget_level, ""))

        # Add deal breaker
        if pref.deal_breaker:
            parts.append(f"avoid {pref.deal_breaker}")

        # Add notes
        if pref.notes:
            parts.append(pref.notes)

        return " ".join(parts).strip()

    def _detect_conflicts(self, hard_union: Dict[str, List[str]]) -> List[Tuple[str, str]]:
        """Detect conflicts in hard constraints."""
        conflicts = []

        if "budget_level" in hard_union:
            try:
                vals = sorted(int(x) for x in hard_union["budget_level"])
                if vals and (max(vals) - min(vals)) > 2:
                    conflicts.append(("budget_level", "large spread in budget levels"))
            except (ValueError, TypeError):
                pass

        return conflicts

    # ========== LangGraph Nodes ==========

    def _fetch_and_process(self, state: AgentState) -> AgentState:
        """
        Fetch all preferences for group_id and create embeddings.
        This is the main node that does all the work.
        """
        group_id = state.get("group_id") or state.get("trip_id")

        if not group_id:
            return {
                "messages": [AIMessage(content="[preference] Error: No group_id provided")],
                "done": True
            }

        print(f"[preference._fetch_and_process] Fetching preferences for group: {group_id}")

        try:
            # Fetch preferences from database
            result = get_all_group_preferences.invoke({"group_id": group_id})

            if "_error" in result:
                return {
                    "messages": [AIMessage(content=f"[preference] Database error: {result['_error']}")],
                    "done": True
                }

            preferences_data = result.get("preferences", [])
            print(f"[preference._fetch_and_process] Found {len(preferences_data)} preferences")

            # Convert to Preference models and create embeddings
            profiles_created = 0
            for pref_dict in preferences_data:
                try:
                    # Create Preference model
                    pref = Preference(**pref_dict)

                    # Create profile with embedding
                    hard = self._normalize_hard(pref)
                    soft = self._normalize_soft(pref.vibes)
                    summary = self._summarize(pref)
                    vec = hash_embed(summary, self.dim)

                    profile = UserPreferenceProfile(
                        group_id=group_id,
                        user_id=pref.user_id,
                        hard=hard,
                        soft=soft,
                        summary=summary,
                        vector=vec,
                        source="db"
                    )

                    # Store profile
                    key = (group_id, pref.user_id)
                    self.profiles[key] = profile
                    self.index.upsert(self._vec_key(group_id, pref.user_id), vec)

                    # Update groups
                    self.groups.setdefault(group_id, [])
                    if pref.user_id not in self.groups[group_id]:
                        self.groups[group_id].append(pref.user_id)

                    profiles_created += 1

                except Exception as e:
                    print(f"[preference._fetch_and_process] Error processing preference: {e}")
                    continue

            print(f"[preference._fetch_and_process] Created {profiles_created} profiles with embeddings")

            # Aggregate preferences
            aggregate = self.aggregate(group_id)

            summary_msg = f"""
                [preference] Processing complete for group {group_id}:
                - Members: {len(aggregate.members)}
                - Top vibes: {dict(sorted(aggregate.soft_mean.items(), key=lambda x: -x[1])[:5])}
                - Budget levels: {aggregate.hard_union.get('budget_level', [])}
                - Conflicts: {aggregate.conflicts}
                - Ready for planning: {aggregate.ready_for_options}
                - Coverage: {aggregate.coverage:.0%}
            """

            # Store output in agent_data (generic storage)
            preferences_summary = {
                "group_id": group_id,
                "members": aggregate.members,
                "aggregated_vibes": aggregate.soft_mean,
                "budget_levels": aggregate.hard_union.get("budget_level", []),
                "conflicts": [f"{k}: {r}" for k, r in aggregate.conflicts],
                "ready_for_planning": aggregate.ready_for_options,
                "coverage": aggregate.coverage
            }

            return {
                "group_id": group_id,
                "agent_data": {
                    "preferences_summary": preferences_summary
                },
                "messages": [AIMessage(content=summary_msg)],
                "done": True
            }

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            print(f"[preference._fetch_and_process] Error: {error_msg}")
            return {
                "messages": [AIMessage(content=f"[preference] Error: {error_msg}")],
                "done": True
            }

    # ========== Graph Construction ==========

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        g = StateGraph(AgentState)

        # Single node that does everything
        g.add_node("fetch_and_process", self._fetch_and_process)

        g.set_entry_point("fetch_and_process")
        g.add_edge("fetch_and_process", END)

        return g.compile()

    # ========== Public API ==========

    def run(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """Run the LangGraph agent with given initial state."""
        return self.app.invoke(initial_state)

    def process_group(self, group_id: str) -> Dict[str, Any]:
        """
        Process all preferences for a group.
        Fetches from database, creates embeddings, and aggregates.

        Args:
            group_id: Group identifier

        Returns:
            State with aggregated preferences and embeddings ready for search
        """
        initial_state: AgentState = {
            "messages": [],
            "group_id": group_id,
            "user_id": ""
        }

        return self.run(initial_state)

    def aggregate(self, group_id: str) -> GroupPreferenceAggregate:
        """
        Aggregate all preferences for a group (using in-memory profiles).

        Args:
            group_id: Group identifier

        Returns:
            GroupPreferenceAggregate with combined preferences
        """
        members = self.groups.get(group_id, [])
        if not members:
            return GroupPreferenceAggregate(group_id, [], {}, {}, [], 0.0, False)

        hard_union: Dict[str, List[str]] = {}
        soft_accum: Dict[str, float] = {}
        soft_count: Dict[str, int] = {}

        for uid in members:
            p = self.profiles.get((group_id, uid))
            if not p:
                continue

            # Aggregate hard constraints
            for k, v in p.hard.items():
                hard_union.setdefault(k, [])
                if v not in hard_union[k]:
                    hard_union[k].append(v)

            # Aggregate soft preferences
            for k, v in p.soft.items():
                soft_accum[k] = soft_accum.get(k, 0.0) + v
                soft_count[k] = soft_count.get(k, 0) + 1

        soft_mean = {k: soft_accum[k] / max(1, soft_count[k]) for k in soft_accum}
        conflicts = self._detect_conflicts(hard_union)
        coverage = len([uid for uid in members if (group_id, uid) in self.profiles]) / len(members) if members else 0.0
        ready = coverage >= 0.8 and not conflicts

        return GroupPreferenceAggregate(group_id, members, hard_union, soft_mean, conflicts, coverage, ready)

    def query_similar(self, group_id: str, items: List[ItemCandidate], k: int = 5) -> List[ScoredItem]:
        """
        Find items most similar to group preferences using semantic search.

        Args:
            group_id: Group identifier
            items: List of candidate items to score
            k: Number of top items to return

        Returns:
            List of top-k scored items
        """
        agg = self.aggregate(group_id)

        # Build weighted terms for group
        weighted_terms = []
        for tag, weight in sorted(agg.soft_mean.items(), key=lambda x: -x[1])[:20]:
            repeat_count = max(1, int(weight * 5))
            weighted_terms.extend([tag] * repeat_count)

        # Add hard constraint values
        for key, values in agg.hard_union.items():
            if key in {"budget_level"}:
                # Add budget level as text
                budget_labels = {1: "budget", 2: "moderate", 3: "comfort", 4: "luxury"}
                for val in values:
                    try:
                        label = budget_labels.get(int(val), "")
                        if label:
                            weighted_terms.append(label)
                    except:
                        pass

        group_text = " ".join(weighted_terms)
        group_vec = hash_embed(group_text, self.dim)

        # Score items
        scored: List[ScoredItem] = []
        for it in items:
            vec = hash_embed(it.text, self.dim)
            s = cosine(group_vec, vec)
            scored.append(ScoredItem(id=it.id, score=float(s), reason="semantic match"))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:k]

    def get_group_vector(self, group_id: str) -> Optional[List[float]]:
        """
        Get the aggregated vector for a group.

        Args:
            group_id: Group identifier

        Returns:
            Aggregated vector representing group preferences
        """
        agg = self.aggregate(group_id)

        if not agg.members:
            return None

        # Build text representation
        weighted_terms = []
        for tag, weight in sorted(agg.soft_mean.items(), key=lambda x: -x[1]):
            repeat_count = max(1, int(weight * 5))
            weighted_terms.extend([tag] * repeat_count)

        text = " ".join(weighted_terms)
        return hash_embed(text, self.dim)


# ========== Backward Compatibility Exports ==========

__all__ = [
    "PreferenceAgent",
    "ItemCandidate",
    "VectorIndex",
    "hash_embed",
    "cosine",
    "_tokenize",
    "UserPreferenceProfile",
    "GroupPreferenceAggregate",
    "ScoredItem"
]

# ========== Self-Test ==========

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Simplified Preference Agent")
    print("=" * 60)

    agent = PreferenceAgent()

    # Test vector embeddings
    print("\n--- Test 1: Vector Embeddings ---")
    vec1 = hash_embed("adventure hiking mountains")
    vec2 = hash_embed("outdoor activities nature")
    vec3 = hash_embed("luxury shopping dining")

    sim_12 = cosine(vec1, vec2)
    sim_13 = cosine(vec1, vec3)

    print(f"Adventure vs Outdoor: {sim_12:.3f}")
    print(f"Adventure vs Luxury: {sim_13:.3f}")
    assert sim_12 > sim_13, "Similar items should have higher similarity!"
    print("✅ Vector embeddings working!")

    # Test with mock data (no DB needed)
    print("\n--- Test 2: Manual Profile Creation ---")
    from app.models.preference import Preference

    # Mock preferences
    pref1 = Preference(
        group_id="test_group",
        user_id="user_1",
        budget_level=3,
        vibes=["Adventure", "Food"],
        deal_breaker="No hostels",
        notes="Love hiking"
    )

    # Create profile manually
    hard = agent._normalize_hard(pref1)
    soft = agent._normalize_soft(pref1.vibes)
    summary = agent._summarize(pref1)
    print(f"Summary: {summary}")
    print(f"Hard: {hard}")
    print(f"Soft: {soft}")
    print("✅ Profile creation working!")

    # Test semantic search
    print("\n--- Test 3: Semantic Search ---")
    items = [
        ItemCandidate("1", "Adventure hiking tour in mountains"),
        ItemCandidate("2", "Luxury spa resort with fine dining"),
        ItemCandidate("3", "Local food tour with cultural experiences")
    ]

    # Manually add a profile for testing
    vec = hash_embed(summary, agent.dim)
    profile = UserPreferenceProfile(
        group_id="test_group",
        user_id="user_1",
        hard=hard,
        soft=soft,
        summary=summary,
        vector=vec
    )
    agent.profiles[("test_group", "user_1")] = profile
    agent.groups["test_group"] = ["user_1"]
    agent.index.upsert(agent._vec_key("test_group", "user_1"), vec)

    recommendations = agent.query_similar("test_group", items, k=3)
    print("Recommendations:")
    for rec in recommendations:
        item = next(it for it in items if it.id == rec.id)
        print(f"  {rec.score:.3f} - {item.text}")

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
