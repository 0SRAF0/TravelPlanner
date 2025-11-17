from __future__ import annotations

import json
import time
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from pydantic.v1 import BaseModel, Field, validator

from app.agents.agent_state import AgentState
from app.core.config import GOOGLE_AI_API_KEY, GOOGLE_AI_MODEL

AGENT_LABEL = "destination_research"


# ====== Models ======

AllowedCategory = Literal["Food", "Nightlife", "Adventure", "Culture", "Relax", "Nature", "Other"]


class PreferencesSummaryIn(BaseModel):
    trip_id: str
    members: list[str]
    aggregated_vibes: dict[str, float]
    budget_levels: list[str]
    conflicts: list[str]
    ready_for_planning: bool
    coverage: float


class DestinationResearchInput(BaseModel):
    preferences_summary: PreferencesSummaryIn
    destination: str
    hints: dict[str, Any] | None = None


class Activity(BaseModel):
    activity_id: str
    name: str
    category: AllowedCategory
    trip_id: str | None = None
    rough_cost: int | None = None
    duration_min: int | None = None
    lat: float | None = None
    lng: float | None = None
    tags: list[str] = Field(default_factory=list)
    fits: list[str] = Field(default_factory=list)
    score: float = 0.0
    rationale: str = ""


class ActivityCatalogOut(BaseModel):
    activity_catalog: list[Activity] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    provenance: list[str] = Field(default_factory=list)

    @validator("metrics", pre=True, always=True)
    def _ensure_metrics_is_dict(cls, value: Any) -> dict[str, Any]:
        if value is None or value == "":
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
                return {}
            except Exception:
                return {}
        return {}


# ====== Utilities ======

_CATEGORY_SET: list[AllowedCategory] = [
    "Food",
    "Nightlife",
    "Adventure",
    "Culture",
    "Relax",
    "Nature",
    "Other",
]
_VIBE_TAGS: dict[str, str] = {
    "adventure": "Adventure",
    "nature": "Nature",
    "food": "Food",
    "culture": "Culture",
    "relax": "Relax",
    "nightlife": "Nightlife",
}

# Budget bands mapping (configurable)
# 1=very cheap, 5=premium
_BUDGET_BANDS: dict[int, tuple[int | None, int | None]] = {
    1: (0, 20),
    2: (20, 50),
    3: (50, 100),
    4: (100, 200),
    5: (200, None),  # open upper bound
}

# Destination centroid cache (filled via geocoding at runtime)
_DEST_CENTROIDS: dict[str, tuple[float, float]] = {}

# ====== Prompt ======

SYSTEM = """
You are the Destination Research Agent.
Given:
- A group preferences summary (members, aggregated vibes 0..1, budget levels 1..5),
- A human-readable destination name,
- Optional hints (radius_km, max_items, preferred_categories),
produce a compact activity_catalog aligned to group vibes, budget, and party makeup.
  
Rules:
- Categories must be one of: Food, Nightlife, Adventure, Culture, Relax, Nature, Other
- Use tags from the same taxonomy (same words as categories).
- Prefer 15-30 items unless max_items is specified; keep diverse categories.
- rough_cost is per-person baseline integer in default project currency; null if unknown.
- duration_min integer or null.
- fits should list member ids who would likely enjoy the activity. If only group vibes available, include all members for top tags.
- score must be 0..1; rank by score desc; tie-break by name asc.
- rationale: short phrase explaining the fit (vibes/budget/diversity).
- Always return a well-formed JSON for ActivityCatalogOut (activity_catalog, insights, warnings, metrics, provenance).
- If results are sparse or uncertain, add actionable insights such as:
  - The 'metrics' field MUST be a JSON object (dictionary). If unknown, return an empty object.
  - Do not return strings, arrays, or numbers for 'metrics'.
  - Return JSON only, with no surrounding prose or code fences.
  - "Broaden radius to 15 km"
  - "Relax budget to include band 4 to 5"
  - "Add Culture to get more daytime options"
"""


def _median_budget(bands: list[str]) -> int:
    vals: list[int] = []
    for b in bands:
        try:
            x = int(b)
        except Exception:
            continue
        if x < 1:
            x = 1
        if x > 5:
            x = 5
        vals.append(x)
    if not vals:
        return 3
    vals.sort()
    m = vals[len(vals) // 2]
    return m


# ====== Agent Implementation ======


class DestinationResearchAgent:
    def __init__(self) -> None:
        self._cache: dict[str, ActivityCatalogOut] = {}
        # Prefer explicit API key; avoid constructing the client without it to prevent ADC requirement in local/test runs
        api_key = GOOGLE_AI_API_KEY
        self.llm = None
        self._llm_unavailable_reason: str = ""
        if api_key:
            try:
                # Import lazily
                from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore

                self.llm = ChatGoogleGenerativeAI(
                    model=GOOGLE_AI_MODEL, temperature=0, api_key=api_key
                )
            except Exception:
                # If client construction fails, continue without LLM; downstream will use fallback
                self.llm = None
                import traceback

                if "langchain_google_genai" in str(traceback.format_exc()):
                    self._llm_unavailable_reason = "langchain_google_genai not installed"
                else:
                    self._llm_unavailable_reason = "Failed to initialize Google LLM client"
                try:
                    self._llm_unavailable_reason += f": {traceback.format_exc(limit=1).strip()}"
                except Exception:
                    pass
        else:
            self._llm_unavailable_reason = "No API key found in GOOGLE_AI_API_KEY"
        self.app = self._build_graph()

    @staticmethod
    def _resolve_destination_centroid(dest: str) -> tuple[float, float] | None:
        """
        Resolve a destination string to a (lat, lng) centroid.
        Strategy:
        1) OpenStreetMap Nominatim geocoding (best-effort)
        2) Fallback to any cached value in _DEST_CENTROIDS (if previously resolved)
        """
        if not dest or not isinstance(dest, str):
            return None
        key = dest.strip().lower()
        if not key:
            return None
        # Best-effort online geocoding (no dependency beyond requests)
        try:
            import requests  # already listed in requirements

            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": dest, "format": "json", "limit": 1},
                headers={"User-Agent": "TravelPlanner/1.0 (+CMPE272)"},
                timeout=5,
            )
            if resp.ok:
                data = resp.json() or []
                if isinstance(data, list) and data:
                    item = data[0]
                    lat = float(item.get("lat"))
                    lon = float(item.get("lon"))
                    # Cache for future runs
                    _DEST_CENTROIDS[key] = (lat, lon)
                    return (lat, lon)
        except Exception:
            # Network/parse failures are tolerated; simply return None
            pass
        # Fallback to cached map if present
        return _DEST_CENTROIDS.get(key)

    @staticmethod
    def _geocode_place(query: str) -> tuple[float, float] | None:
        """
        Best-effort geocoding for a place/activity name using Nominatim.
        Returns (lat, lng) or None.
        """
        if not query or not isinstance(query, str):
            return None
        try:
            import requests

            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1},
                headers={"User-Agent": "TravelPlanner/1.0 (+CMPE272)"},
                timeout=5,
            )
            if resp.ok:
                data = resp.json() or []
                if isinstance(data, list) and data:
                    item = data[0]
                    return (float(item.get("lat")), float(item.get("lon")))
        except Exception:
            pass
        return None

    # ---- Node ----
    def _build_catalog(self, state: AgentState) -> AgentState:
        t0 = time.time()
        agent_data = dict(state.get("agent_data", {}) or {})

        hints = state.get("hints") or agent_data.get("hints") or {}
        force = bool((hints or {}).get("force", False))
        if agent_data.get("activity_catalog") and not force:
            # Short circuit
            return state

        # Flexible input locations: top-level or agent_data
        pref = state.get("preferences_summary") or agent_data.get("preferences_summary")
        dest = state.get("destination") or agent_data.get("destination")

        insights: list[str] = []
        warnings: list[str] = []

        if not dest or not isinstance(dest, str) or not dest.strip():
            warnings.append("Missing destination")
            insights.append("Provide a destination like 'City, Country'")
            out = ActivityCatalogOut(
                activity_catalog=[],
                insights=insights,
                warnings=warnings,
                metrics={
                    "candidates_total": 0,
                    "candidates_after_filters": 0,
                    "final_selected": 0,
                    "latency_ms": int((time.time() - t0) * 1000),
                },
                provenance=[],
            )
            agent_data.update(out.dict())
            state["agent_data"] = agent_data
            return state

        # Validate preferences
        try:
            ps = PreferencesSummaryIn(**pref)  # type: ignore[arg-type]
        except Exception:
            warnings.append("Invalid preferences_summary; using defaults")
            # Default minimal usable
            ps = PreferencesSummaryIn(
                trip_id=state.get("trip_id") or "trip",
                members=list(state.get("members", [])) or [],
                aggregated_vibes={},
                budget_levels=[],
                conflicts=[],
                ready_for_planning=True,
                coverage=1.0,
            )

        if not ps.ready_for_planning or not ps.members:
            warnings.append("Not ready for planning or no members")
            insights.append("Collect preferences from all members first")
            out = ActivityCatalogOut(
                activity_catalog=[],
                insights=insights,
                warnings=warnings,
                metrics={
                    "candidates_total": 0,
                    "candidates_after_filters": 0,
                    "final_selected": 0,
                    "latency_ms": int((time.time() - t0) * 1000),
                },
                provenance=[],
            )
            agent_data.update(out.dict())
            state["agent_data"] = agent_data
            return state

        dest_key = dest.strip().lower()
        trip_id = ps.trip_id or (state.get("trip_id") or "trip")
        radius_km = float((hints or {}).get("radius_km", 10.0))
        max_items = int((hints or {}).get("max_items", 20))
        preferred_categories = list((hints or {}).get("preferred_categories") or [])

        # Log start of generation
        try:
            print("\n" + "=" * 80)
            print("  DESTINATION RESEARCH START")
            print("=" * 80)
            print(f"Trip: {trip_id}")
            print(f"Destination: {dest}")
            print(f"Radius (km): {radius_km}")
            print(f"Max items: {max_items}")
            print(f"Preferred categories: {preferred_categories}")
        except Exception:
            pass

        cache_key = (
            f"{trip_id}|{dest_key}|{radius_km}|{max_items}|{','.join(sorted(preferred_categories))}"
        )
        if cache_key in self._cache and not force:
            cached = self._cache[cache_key]
            agent_data.update(cached.dict())
            state["agent_data"] = agent_data
            return state

        # Prepare LLM call
        group_budget_band = _median_budget(ps.budget_levels)
        payload = {
            "destination": dest,
            "preferences_summary": ps.dict(),
            "hints": {
                "radius_km": radius_km,
                "max_items": max_items,
                "preferred_categories": preferred_categories,
            },
            "budget_band_mapping": _BUDGET_BANDS,
            "group_budget_band": group_budget_band,
            "categories": _CATEGORY_SET,
        }

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM),
                ("user", "Input:\n{payload}\n\nReturn JSON only."),
            ]
        )

        # If LLM is not available, or invocation fails, return a helpful fallback
        if self.llm is None:
            if self._llm_unavailable_reason:
                print(f"[destination_research] LLM unavailable: {self._llm_unavailable_reason}")
            insights = [
                "Broaden radius to 15 km",
                "Relax budget to include band 4 to 5",
                "Add Culture to get more daytime options",
            ]
            out = ActivityCatalogOut(
                activity_catalog=[],
                insights=insights,
                warnings=[
                    "LLM unavailable; no activities generated",
                    f"Reason: {self._llm_unavailable_reason}",
                ]
                if self._llm_unavailable_reason
                else ["LLM unavailable; no activities generated"],
                metrics={
                    "candidates_total": 0,
                    "candidates_after_filters": 0,
                    "final_selected": 0,
                    "latency_ms": int((time.time() - t0) * 1000),
                },
                provenance=["llm_unavailable"],
            )
            agent_data.update(out.dict())
            state["agent_data"] = agent_data
            return state

        structured_llm = self.llm.with_structured_output(ActivityCatalogOut)
        run = prompt | structured_llm
        try:
            result: ActivityCatalogOut = run.invoke({"payload": payload})
        except Exception as e:
            err_text = f"{type(e).__name__}: {e}"
            print(f"[destination_research] LLM invocation failed: {err_text}")
            # Fallback: empty catalog with actionable insights
            insights = [
                "Broaden radius to 15 km",
                "Relax budget to include band 4 to 5",
                "Add Culture to get more daytime options",
            ]
            out = ActivityCatalogOut(
                activity_catalog=[],
                insights=insights,
                warnings=[
                    "LLM unavailable or failed; no activities generated",
                    f"Error: {err_text}",
                ],
                metrics={
                    "candidates_total": 0,
                    "candidates_after_filters": 0,
                    "final_selected": 0,
                    "latency_ms": int((time.time() - t0) * 1000),
                },
                provenance=["llm_failed"],
            )
            agent_data.update(out.dict())
            state["agent_data"] = agent_data
            return state

        # Post-process: determinism and metrics
        selected = list(result.activity_catalog or [])
        # Fill in missing trip_id and try to geocode coordinates for each activity.
        # If geocoding fails, default both to destination centroid for map visualization.
        centroid = DestinationResearchAgent._resolve_destination_centroid(dest)
        for a in selected:
            if getattr(a, "trip_id", None) in (None, ""):
                a.trip_id = trip_id
            lat_none = getattr(a, "lat", None) is None
            lng_none = getattr(a, "lng", None) is None
            if lat_none or lng_none:
                # Try to geocode the activity name scoped by destination
                query = f"{getattr(a, 'name', '')}, {dest}".strip().strip(",")
                coords = DestinationResearchAgent._geocode_place(query)
                if coords is not None:
                    a.lat, a.lng = coords
                elif centroid is not None:
                    # Last resort: use destination centroid so map pins render
                    a.lat, a.lng = centroid

        selected.sort(
            key=lambda a: (-float(getattr(a, "score", 0.0) or 0.0), getattr(a, "name", "").lower())
        )

        metrics = dict(result.metrics or {})
        metrics.update(
            {
                "candidates_total": metrics.get("candidates_total", len(selected)),
                "candidates_after_filters": metrics.get("candidates_after_filters", len(selected)),
                "final_selected": len(selected),
                "latency_ms": int((time.time() - t0) * 1000),
                "trip_id": trip_id,
                "destination": dest,
                "radius_km": radius_km,
                "preferred_categories": preferred_categories,
            }
        )

        out = ActivityCatalogOut(
            activity_catalog=selected[:max_items],
            insights=result.insights or [],
            warnings=warnings + (result.warnings or []),
            metrics=metrics,
            provenance=(result.provenance or []) + ["llm"],
        )

        agent_data.update(out.dict())
        state["agent_data"] = agent_data

        # Cache by trip_id to be idempotent
        self._cache[cache_key] = out

        # Add message for traceability
        state.setdefault("messages", [])
        state["messages"].append(
            AIMessage(
                content=f"[destination_research] Completed for trip {trip_id}. Selected={len(selected)}"
            )
        )

        # Log completion summary
        try:
            print("\n" + "=" * 80)
            print("  DESTINATION RESEARCH COMPLETE")
            print("=" * 80)
            print(f"Trip: {trip_id}")
            print(f"Destination: {dest}")
            print(f"Activities generated: {len(out.activity_catalog)}")
            if out.activity_catalog:
                sample_names = [getattr(a, "name", "") for a in out.activity_catalog[:5]]
                print(f"Sample activities: {sample_names}")
            if out.warnings:
                print(f"Warnings: {out.warnings}")
            print(f"Latency (ms): {metrics.get('latency_ms')}")
        except Exception:
            pass
        return state

    # ---- Graph ----
    def _build_graph(self) -> StateGraph:
        g = StateGraph(AgentState)
        g.add_node("build_catalog", self._build_catalog)
        g.set_entry_point("build_catalog")
        g.add_edge("build_catalog", END)
        return g.compile()

    # ---- Public API ----
    def run(self, initial_state: dict[str, Any]) -> dict[str, Any]:
        return self.app.invoke(initial_state)


__all__ = [
    "DestinationResearchAgent",
    "Activity",
    "ActivityCatalogOut",
    "PreferencesSummaryIn",
    "DestinationResearchInput",
]
