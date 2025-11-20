# preference_agent.py - Simplified agent for aggregation and semantic search
from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from datetime import datetime
from bson import ObjectId

from app.agents.agent_state import AgentState
from app.agents.tools import get_all_trip_preferences
from app.models.preference import Preference
from app.db.database import get_database

AGENT_LABEL = "preference"

# ========== Vector Embedding Utilities ==========

# Global embedding model (lazy-loaded)
_embedding_model = None


def get_embedding_model():
    """Lazy-load the sentence transformer model."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer

            # Using a lightweight, fast model optimized for semantic similarity
            _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            print("[preference] Loaded sentence-transformers model: all-MiniLM-L6-v2")
        except Exception as e:
            print(f"[preference] Warning: Could not load sentence-transformers: {e}")
            _embedding_model = None
    return _embedding_model


def embed_text(text: str) -> list[float]:
    """
    Create semantic embedding vector using sentence-transformers.
    Falls back to simple hash-based embedding if model not available.
    """
    model = get_embedding_model()
    if model is not None:
        try:
            # sentence-transformers returns numpy array
            embedding = model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            print(f"[preference] Embedding error: {e}, falling back to hash")

    # Fallback: simple hash-based embedding
    return _hash_embed_fallback(text, dim=384)


def _hash_embed_fallback(text: str, dim: int = 384) -> list[float]:
    """Fallback hash-based embedding if sentence-transformers unavailable."""
    import hashlib

    v = [0.0] * dim
    for char in "/,;:.-()[]{}!?":
        text = text.replace(char, " ")
    tokens = [t for t in text.lower().split() if t]

    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        i = h % dim
        v[i] += 1.0
    # L2 normalize
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    return sum(x * y for x, y in zip(a, b, strict=False))


# ========== Data Models ==========


@dataclass
class SurveyInput:
    """Input model for user preference survey."""

    text: str | None = None  # free-form: vibes, notes, activities
    hard: dict[str, str] = field(
        default_factory=dict
    )  # e.g., {"budget_level":"3","deal_breakers":"No early mornings"}
    soft: dict[str, float] = field(
        default_factory=dict
    )  # weighted tags 0..1, e.g., {"adventure":0.9,"food":0.8,"nature":0.7}


@dataclass
class UserPreferenceProfile:
    """Complete user preference profile with embedding."""

    trip_id: str
    user_id: str
    hard: dict[str, str]
    soft: dict[str, float]
    summary: str
    vector: list[float]
    version: int = 1
    source: str = "db"
    updated_at: float = field(default_factory=lambda: time.time())


@dataclass
class TripPreferenceAggregate:
    """Aggregated preferences for entire trip."""

    trip_id: str
    members: list[str]
    hard_union: dict[str, list[str]]
    soft_mean: dict[str, float]
    conflicts: list[tuple[str, str]]
    coverage: float  # 0..1
    ready_for_options: bool


@dataclass
class ItemCandidate:
    """Candidate item for recommendation."""

    id: str
    text: str
    meta: dict[str, str] = field(default_factory=dict)


@dataclass
class ScoredItem:
    """Item with similarity score."""

    id: str
    score: float
    reason: str


@dataclass
class UpdateDelta:
    """Represents changes made during an update."""

    changed: dict[str, tuple[str, str]]  # field -> (old_value, new_value)


# ========== Vector Index ==========


class VectorIndex:
    """In-memory vector index for semantic search."""

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.vectors: dict[str, list[float]] = {}

    def upsert(self, key: str, vec: list[float]) -> None:
        if len(vec) != self.dim:
            raise ValueError("vector dim mismatch")
        self.vectors[key] = vec

    def get(self, key: str) -> list[float] | None:
        return self.vectors.get(key)


# ========== Preference Agent ==========


class PreferenceAgent:
    """
    Preference agent for aggregation and semantic search.

    Responsibilities:
    - Fetch preferences from database by trip_id
    - Create vector embeddings for semantic search
    - Aggregate trip preferences
    - Provide recommendations via semantic similarity

    NOT responsible for:
    - Saving preferences (handled by FastAPI endpoints)
    - Validating input (handled by Pydantic models)
    """

    def __init__(self, model_name: str | None = None, dim: int | None = None):
        self.model_name = model_name or "gemini-pro"

        # Determine embedding dimension
        if dim is None:
            # Try to get dimension from embedding model
            emb_model = get_embedding_model()
            if emb_model is not None:
                # all-MiniLM-L6-v2 produces 384-dimensional vectors
                self.dim = emb_model.get_sentence_embedding_dimension()
            else:
                # Fallback dimension for hash-based embeddings
                self.dim = 384
        else:
            self.dim = dim

        # In-memory storage
        self.index = VectorIndex(self.dim)
        self.profiles: dict[tuple[str, str], UserPreferenceProfile] = {}
        self.trips: dict[str, list[str]] = {}

        # LLM (optional, lazy-loaded)
        self._llm = None
        # Build LangGraph app for this agent
        self.app = self._build_graph()

    # Note: PreferenceAgent does NOT use LLM - it only does aggregation and vector embeddings
    # No LLM calls = no API quota usage for preference processing

    # ========== Vector Embedding Methods ==========

    def _vec_key(self, trip_id: str, user_id: str) -> str:
        """Generate vector key."""
        raw = f"{trip_id}:{user_id}:prefs"
        short = hashlib.md5(raw.encode("utf-8")).hexdigest()[:6]
        return f"vec_{short}"

    def _normalize_hard(self, pref: Preference) -> dict[str, str]:
        """Extract hard constraints from Preference model."""
        hard = {}
        if pref.budget_level:
            hard["budget_level"] = str(pref.budget_level)
        if pref.deal_breaker:
            hard["deal_breaker"] = pref.deal_breaker
        return hard

    def _normalize_soft(self, vibes: list[str]) -> dict[str, float]:
        """Convert vibes list to weighted soft preferences."""
        # Assign decreasing weights: 0.9, 0.8, 0.7, ...
        soft = {}
        for i, vibe in enumerate(vibes[:6]):  # Max 6 vibes
            weight = max(0.5, 0.9 - (i * 0.1))
            soft[vibe.lower()] = weight
        return soft

    def _normalize_deal_breakers(self, text: str) -> list[str]:
        """
        Normalize deal breaker text into a list of individual deal breakers.

        Splits on commas/semicolons, trims whitespace, strips trailing punctuation.
        """
        if not text:
            return []
        # Split on commas/semicolons; trim whitespace; strip trailing sentence punctuation
        parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
        cleaned = [p.rstrip(".!?:;").strip() for p in parts if p]
        return cleaned

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

    def _detect_conflicts(self, hard_union: dict[str, list[str]]) -> list[tuple[str, str]]:
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

    async def _fetch_and_process(self, state: AgentState) -> AgentState:
        """
        Fetch all preferences for trip_id and create embeddings.
        This is the main node that does all the work.
        """
        t0 = time.time()
        trip_id = state.get("trip_id") or state.get("trip_id")

        if not trip_id:
            return {
                "messages": [AIMessage(content="[preference] Error: No trip_id provided")],
                "done": True,
            }

        print("\n" + "=" * 80)
        print("  PREFERENCE AGENT START")
        print("=" * 80)
        print(f"[DEBUG] Trip ID: {trip_id}")
        print(f"[PERF] Start timestamp: {time.time()}")

        try:
            # Fetch preferences from database (async tool)
            fetch_start = time.time()
            print(f"[DB] Fetching preferences from database...")
            result = await get_all_trip_preferences.ainvoke({"trip_id": trip_id})
            fetch_latency = (time.time() - fetch_start) * 1000
            print(f"[DB] ✅ Database fetch completed")
            print(f"[PERF] Database fetch latency: {fetch_latency:.2f}ms")

            if "_error" in result:
                return {
                    "messages": [
                        AIMessage(content=f"[preference] Database error: {result['_error']}")
                    ],
                    "done": True,
                }

            preferences_data = result.get("preferences", [])
            print(f"[DEBUG] Found {len(preferences_data)} preferences in database")
            print(f"[DEBUG] Input data sizes:")
            print(f"  - Preference count: {len(preferences_data)}")

            # Convert to Preference models and create embeddings
            embed_start = time.time()
            profiles_created = 0
            embedding_times = []
            
            print(f"[PROCESSING] Creating embeddings for {len(preferences_data)} preferences...")
            for idx, pref_dict in enumerate(preferences_data, 1):
                try:
                    item_start = time.time()
                    
                    # Create Preference model
                    pref = Preference(**pref_dict)

                    # Create profile with embedding
                    hard = self._normalize_hard(pref)
                    soft = self._normalize_soft(pref.vibes)
                    summary = self._summarize(pref)
                    
                    # Track embedding generation time
                    emb_start = time.time()
                    vec = embed_text(summary)
                    emb_time = (time.time() - emb_start) * 1000
                    embedding_times.append(emb_time)

                    profile = UserPreferenceProfile(
                        trip_id=trip_id,
                        user_id=pref.user_id,
                        hard=hard,
                        soft=soft,
                        summary=summary,
                        vector=vec,
                        source="db",
                    )

                    # Store profile
                    key = (trip_id, pref.user_id)
                    self.profiles[key] = profile
                    self.index.upsert(self._vec_key(trip_id, pref.user_id), vec)

                    # Update trips
                    self.trips.setdefault(trip_id, [])
                    if pref.user_id not in self.trips[trip_id]:
                        self.trips[trip_id].append(pref.user_id)

                    profiles_created += 1
                    item_latency = (time.time() - item_start) * 1000
                    
                    if idx % 5 == 0 or idx == len(preferences_data):  # Log every 5th or last
                        print(f"[PROCESSING] Processed {idx}/{len(preferences_data)} preferences (last item: {item_latency:.2f}ms)")

                except Exception as e:
                    print(f"[ERROR] Failed to process preference {idx}/{len(preferences_data)}: {type(e).__name__}: {e}")
                    continue

            embed_total_latency = (time.time() - embed_start) * 1000
            avg_embedding_time = sum(embedding_times) / len(embedding_times) if embedding_times else 0
            
            print(f"[PROCESSING] ✅ Created {profiles_created} profiles with embeddings")
            print(f"[PERF] Total embedding generation time: {embed_total_latency:.2f}ms")
            print(f"[PERF] Average embedding time per preference: {avg_embedding_time:.2f}ms")

            # Aggregate preferences
            agg_start = time.time()
            print(f"[PROCESSING] Computing preference aggregation...")
            aggregate = self.aggregate(trip_id)
            agg_latency = (time.time() - agg_start) * 1000
            print(f"[PERF] Aggregation latency: {agg_latency:.2f}ms")

            # Log detailed aggregation results
            print("\n" + "=" * 80)
            print("  PREFERENCE AGENT COMPLETE")
            print("=" * 80)
            print(f"[RESULT] Trip: {trip_id}")
            print(f"[RESULT] Members: {len(aggregate.members)}")
            print(f"[RESULT] Coverage: {aggregate.coverage:.0%} ({len(aggregate.members)} members)")
            print(f"[RESULT] Ready for planning: {aggregate.ready_for_options}")
            
            if aggregate.soft_mean:
                top_vibes = dict(sorted(aggregate.soft_mean.items(), key=lambda x: -x[1])[:5])
                print(f"[RESULT] Top 5 vibes:")
                for vibe, score in top_vibes.items():
                    print(f"  - {vibe}: {score:.2f}")
            
            budget_levels = aggregate.hard_union.get("budget_level", [])
            if budget_levels:
                print(f"[RESULT] Budget levels: {budget_levels}")
            
            if aggregate.conflicts:
                print(f"[WARN] Conflicts detected:")
                for key, reason in aggregate.conflicts:
                    print(f"  - {key}: {reason}")
            
            total_latency = (time.time() - t0) * 1000
            print(f"[PERF] Total preference agent latency: {total_latency:.2f}ms ({total_latency/1000:.2f}s)")
            
            summary_msg = f"""
                [preference] Processing complete for trip {trip_id}:
                - Members: {len(aggregate.members)}
                - Top vibes: {dict(sorted(aggregate.soft_mean.items(), key=lambda x: -x[1])[:5])}
                - Budget levels: {aggregate.hard_union.get("budget_level", [])}
                - Conflicts: {aggregate.conflicts}
                - Ready for planning: {aggregate.ready_for_options}
                - Coverage: {aggregate.coverage:.0%}
            """
            # Aggregate destinations - pick most common
            destinations = []
            for pref_dict in preferences_data:
                if pref_dict.get('destination'):
                    destinations.append(pref_dict['destination'])

            from collections import Counter
            common_destination = None
            if destinations:
                common_destination = Counter(destinations).most_common(1)[0][0]
    
            # Store output in agent_data (generic storage)
            preferences_summary = {
                "trip_id": trip_id,
                "members": aggregate.members,
                "destination": common_destination,
                "aggregated_vibes": aggregate.soft_mean,
                "budget_levels": aggregate.hard_union.get("budget_level", []),
                "conflicts": [f"{k}: {r}" for k, r in aggregate.conflicts],
                "ready_for_planning": aggregate.ready_for_options,
                "coverage": aggregate.coverage,
            }

            # Preserve existing agent_data and optionally set destination if missing
            agent_data_out = dict(state.get("agent_data", {}) or {})
            agent_data_out["preferences_summary"] = preferences_summary

            # If destination is missing, suggest fallback ONLY if not in destination_decision phase
            current_destination = str(agent_data_out.get("destination") or "").strip()
            phase_tracking = agent_data_out.get("phase_tracking", {})
            current_phase = phase_tracking.get("current_phase")
            
            if not current_destination:
                # Don't suggest destination if we're in destination_decision phase (users are voting)
                if current_phase == "destination_decision":
                    print("[preference] No destination set, but destination_decision phase is active - waiting for consensus")
                    agent_data_out["destination"] = None
                else:
                    # Determine top vibe
                    top_vibe = None
                    if aggregate.soft_mean:
                        top_vibe = max(aggregate.soft_mean.items(), key=lambda kv: kv[1])[0]
                    # Simple mapping from top vibe to a reasonable default destination
                    vibe_to_destination = {
                        "adventure": "Queenstown, New Zealand",
                        "nature": "Banff, Canada",
                        "food": "Tokyo, Japan",
                        "culture": "Rome, Italy",
                        "relax": "Bali, Indonesia",
                        "nightlife": "Las Vegas, USA",
                    }
                    suggested_destination = vibe_to_destination.get(
                        (top_vibe or "").lower(), "San Francisco, USA"
                    )
                    agent_data_out["destination"] = suggested_destination
                    print(
                        f"[preference] No destination set; suggesting '{suggested_destination}'"
                        + (f" based on top vibe '{top_vibe}'" if top_vibe else "")
                    )
                # Best-effort: persist to trips collection
                try:
                    db = get_database()
                    trips = db.trips
                    try:
                        await trips.update_one(
                            {"_id": ObjectId(trip_id)},
                            {"$set": {"destination": suggested_destination, "updated_at": datetime.utcnow()}},
                        )
                    except Exception:
                        # If trip_id is not a valid ObjectId, skip persistence
                        pass
                except Exception as e:
                    print(f"[preference] Warning: failed to persist suggested destination: {e}")

            return {
                "trip_id": trip_id,
                "agent_data": agent_data_out,
                "messages": [AIMessage(content=summary_msg)],
                "done": True,
            }

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            print(f"[preference._fetch_and_process] Error: {error_msg}")
            return {
                "messages": [AIMessage(content=f"[preference] Error: {error_msg}")],
                "done": True,
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

    def run(self, initial_state: dict[str, Any]) -> dict[str, Any]:
        """Run the LangGraph agent with given initial state."""
        return self.app.invoke(initial_state)

    def process_trip(self, trip_id: str) -> dict[str, Any]:
        """
        Process all preferences for a trip.
        Fetches from database, creates embeddings, and aggregates.

        Args:
            trip_id: Trip identifier

        Returns:
            State with aggregated preferences and embeddings ready for search
        """
        initial_state: AgentState = {"messages": [], "trip_id": trip_id, "user_id": ""}

        return self.run(initial_state)

    def aggregate(self, trip_id: str) -> TripPreferenceAggregate:
        """
        Aggregate all preferences for a trip (using in-memory profiles).

        Args:
            trip_id: Trip identifier

        Returns:
            TripPreferenceAggregate with combined preferences
        """
        members = self.trips.get(trip_id, [])
        if not members:
            return TripPreferenceAggregate(trip_id, [], {}, {}, [], 0.0, False)

        hard_union: dict[str, list[str]] = {}
        soft_accum: dict[str, float] = {}
        soft_count: dict[str, int] = {}

        for uid in members:
            p = self.profiles.get((trip_id, uid))
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
        coverage = (
            len([uid for uid in members if (trip_id, uid) in self.profiles]) / len(members)
            if members
            else 0.0
        )
        ready = coverage >= 0.8 and not conflicts

        return TripPreferenceAggregate(
            trip_id, members, hard_union, soft_mean, conflicts, coverage, ready
        )

    def ingest_survey(
        self, trip_id: str, user_id: str, survey: SurveyInput
    ) -> UserPreferenceProfile:
        """
        Manually ingest a user preference survey (for testing/direct input).

        Args:
            trip_id: Trip identifier
            user_id: User identifier
            survey: SurveyInput with text, hard constraints, and soft preferences

        Returns:
            UserPreferenceProfile created from the survey
        """
        # Use survey data directly
        hard = survey.hard.copy() if survey.hard else {}
        soft = survey.soft.copy() if survey.soft else {}
        summary = survey.text or ""

        # Create embedding
        vec = embed_text(summary)

        # Create profile
        profile = UserPreferenceProfile(
            trip_id=trip_id,
            user_id=user_id,
            hard=hard,
            soft=soft,
            summary=summary,
            vector=vec,
            source="survey",
        )

        # Store profile
        key = (trip_id, user_id)
        self.profiles[key] = profile
        self.index.upsert(self._vec_key(trip_id, user_id), vec)

        # Update trips
        self.trips.setdefault(trip_id, [])
        if user_id not in self.trips[trip_id]:
            self.trips[trip_id].append(user_id)

        return profile

    def update(self, trip_id: str, user_id: str, updates: dict[str, str]) -> UpdateDelta:
        """
        Update specific fields in a user's preference profile.

        Args:
            trip_id: Trip identifier
            user_id: User identifier
            updates: Dictionary of field paths to new values (e.g., {"hard.budget_level": "4"})

        Returns:
            UpdateDelta showing what changed
        """
        key = (trip_id, user_id)
        profile = self.profiles.get(key)

        if not profile:
            raise ValueError(f"No profile found for trip={trip_id}, user={user_id}")

        changed = {}

        for field_path, new_value in updates.items():
            if field_path.startswith("hard."):
                field_name = field_path.split(".", 1)[1]
                old_value = profile.hard.get(field_name, "")
                profile.hard[field_name] = new_value
                changed[field_path] = (old_value, new_value)

            elif field_path.startswith("soft."):
                field_name = field_path.split(".", 1)[1]
                old_value = str(profile.soft.get(field_name, 0.0))
                try:
                    profile.soft[field_name] = float(new_value)
                    changed[field_path] = (old_value, new_value)
                except ValueError:
                    pass

        # Update profile version and timestamp
        profile.version += 1
        profile.updated_at = time.time()

        # Store updated profile
        self.profiles[key] = profile

        return UpdateDelta(changed=changed)

    def query_similar(
        self, trip_id: str, items: list[ItemCandidate], k: int = 5
    ) -> list[ScoredItem]:
        """
        Find items most similar to trip preferences using semantic search.

        Args:
            trip_id: Trip identifier
            items: List of candidate items to score
            k: Number of top items to return

        Returns:
            List of top-k scored items
        """
        agg = self.aggregate(trip_id)

        # Build weighted terms for trip
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
                    except (ValueError, TypeError, AttributeError):
                        pass

        trip_text = " ".join(weighted_terms)
        trip_vec = embed_text(trip_text)

        # Score items
        scored: list[ScoredItem] = []
        for it in items:
            vec = embed_text(it.text)
            s = cosine(trip_vec, vec)
            scored.append(ScoredItem(id=it.id, score=float(s), reason="semantic match"))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:k]

    def get_trip_vector(self, trip_id: str) -> list[float] | None:
        """
        Get the aggregated vector for a trip.

        Args:
            trip_id: Trip identifier

        Returns:
            Aggregated vector representing trip preferences
        """
        agg = self.aggregate(trip_id)

        if not agg.members:
            return None

        # Build text representation
        weighted_terms = []
        for tag, weight in sorted(agg.soft_mean.items(), key=lambda x: -x[1]):
            repeat_count = max(1, int(weight * 5))
            weighted_terms.extend([tag] * repeat_count)

        text = " ".join(weighted_terms)
        return embed_text(text)


# ========== Backward Compatibility Exports ==========

__all__ = [
    "PreferenceAgent",
    "ItemCandidate",
    "VectorIndex",
    "embed_text",
    "cosine",
    "get_embedding_model",
    "UserPreferenceProfile",
    "TripPreferenceAggregate",
    "ScoredItem",
    "SurveyInput",
    "UpdateDelta",
]
