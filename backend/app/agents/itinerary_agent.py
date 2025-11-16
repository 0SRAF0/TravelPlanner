from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Literal
from pydantic.v1 import BaseModel, Field, validator
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
import os
import time
import json

from app.agents.agent_state import AgentState
from app.agents.destination_research_agent import Activity, PreferencesSummaryIn
from app.core.config import GOOGLE_AI_MODEL, GOOGLE_AI_API_KEY


AGENT_LABEL = "itinerary_generation"


# ====== Models ======

class ItineraryItem(BaseModel):
    activity_id: str
    name: str
    start_time: str = Field(description="Start time in HH:MM format (24-hour)")
    end_time: str = Field(description="End time in HH:MM format (24-hour)")
    notes: Optional[str] = Field(default=None, description="Short notes or tips for this activity")
    lat: Optional[float] = None
    lng: Optional[float] = None
    category: Optional[str] = None
    rough_cost: Optional[int] = None
    duration_min: Optional[int] = None


class DayItinerary(BaseModel):
    day: int = Field(description="Day number, starting from 1")
    date: Optional[str] = Field(default=None, description="Optional date for the day (YYYY-MM-DD)")
    items: List[ItineraryItem] = Field(default_factory=list)


class ItineraryOut(BaseModel):
    itinerary: List[DayItinerary] = Field(default_factory=list)
    insights: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    provenance: List[str] = Field(default_factory=list)

    @validator("metrics", pre=True, always=True)
    def _ensure_metrics_is_dict(cls, value: Any) -> Dict[str, Any]:
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


class ItineraryGenerationInput(BaseModel):
    preferences_summary: PreferencesSummaryIn
    destination: str
    activity_catalog: List[Activity]
    trip_duration_days: int = Field(default=3, description="Number of days for the trip")
    start_date: Optional[str] = Field(default=None, description="Optional start date for the trip (YYYY-MM-DD)")
    hints: Optional[Dict[str, Any]] = None


# ====== Prompt ======

SYSTEM = """
You are the Itinerary Generation Agent.
Given:
- A group preferences summary (members, aggregated vibes 0..1, budget levels 1..5),
- A human-readable destination name,
- A catalog of available activities for the destination,
- The desired trip duration in days,
- An optional start date for the trip,
- Optional hints (e.g., "focus on adventure", "include free time"),
produce a detailed daily itinerary.

Rules:
- Create a balanced itinerary that aligns with the group's aggregated vibes and budget.
- Use activities ONLY from the provided `activity_catalog`. Do not invent new activities.
- Each activity should have a `start_time` and `end_time` in HH:MM (24-hour) format.
- Ensure activities are logically sequenced and allow for travel time between locations if coordinates are available.
- Try to fill each day with a reasonable number of activities (e.g., 3-5 main activities).
- Include `notes` for each activity if there are specific tips or rationale.
- If a `start_date` is provided, use it to populate the `date` field for each day.
- The `day` field should start from 1.
- Always return a well-formed JSON for ItineraryOut (itinerary, insights, warnings, metrics, provenance).
- If results are sparse or uncertain, add actionable insights.
- The 'metrics' field MUST be a JSON object (dictionary). If unknown, return an empty object.
- Do not return strings, arrays, or numbers for 'metrics'.
- Return JSON only, with no surrounding prose or code fences.
"""


# ====== Agent Implementation ======

class ItineraryAgent:
    def __init__(self) -> None:
        self._cache: Dict[str, ItineraryOut] = {}
        api_key = GOOGLE_AI_API_KEY
        self.llm = None
        self._llm_unavailable_reason: str = ""
        if api_key:
            try:
                self.llm = ChatGoogleGenerativeAI(model=GOOGLE_AI_MODEL, temperature=0.7, api_key=api_key)
            except Exception:
                self.llm = None
                import traceback
                self._llm_unavailable_reason = "Failed to initialize Google LLM client"
                try:
                    self._llm_unavailable_reason += f": {traceback.format_exc(limit=1).strip()}"
                except Exception:
                    pass
        else:
            self._llm_unavailable_reason = "No API key found in GOOGLE_AI_API_KEY"
        self.app = self._build_graph()

    # ---- Node ----
    def _build_itinerary(self, state: AgentState) -> AgentState:
        t0 = time.time()
        agent_data = dict(state.get("agent_data", {}) or {})

        hints = state.get("hints") or agent_data.get("hints") or {}
        force = bool((hints or {}).get("force", False))
        if agent_data.get("itinerary") and not force:
            # Short circuit
            return state

        # Flexible input locations: top-level or agent_data
        pref_summary = state.get("preferences_summary") or agent_data.get("preferences_summary")
        destination = state.get("destination") or agent_data.get("destination")
        activity_catalog = state.get("activity_catalog") or agent_data.get("activity_catalog")
        trip_duration_days = state.get("trip_duration_days") or agent_data.get("trip_duration_days", 3)
        start_date = state.get("start_date") or agent_data.get("start_date")

        insights: List[str] = []
        warnings: List[str] = []

        if not pref_summary:
            warnings.append("Missing preferences summary")
            insights.append("Ensure preferences are processed by the PreferenceAgent")
        if not destination:
            warnings.append("Missing destination")
            insights.append("Provide a destination like 'City, Country'")
        if not activity_catalog:
            warnings.append("Missing activity catalog")
            insights.append("Ensure destination research is performed by the DestinationResearchAgent")

        if warnings:
            out = ItineraryOut(
                itinerary=[],
                insights=insights,
                warnings=warnings,
                metrics={"latency_ms": int((time.time() - t0) * 1000)},
                provenance=[],
            )
            agent_data.update(out.dict())
            state["agent_data"] = agent_data
            return state

        # Validate inputs
        try:
            input_data = ItineraryGenerationInput(
                preferences_summary=PreferencesSummaryIn(**pref_summary), # type: ignore
                destination=destination, # type: ignore
                activity_catalog=[Activity(**a) for a in activity_catalog], # type: ignore
                trip_duration_days=trip_duration_days, # type: ignore
                start_date=start_date, # type: ignore
                hints=hints
            )
        except Exception as e:
            warnings.append(f"Invalid input data: {e}")
            out = ItineraryOut(
                itinerary=[],
                insights=["Check input format for preferences, destination, and activity catalog."],
                warnings=warnings,
                metrics={"latency_ms": int((time.time() - t0) * 1000)},
                provenance=[],
            )
            agent_data.update(out.dict())
            state["agent_data"] = agent_data
            return state

        trip_id = input_data.preferences_summary.trip_id or (state.get("trip_id") or "trip")
        cache_key = f"{trip_id}|{input_data.destination}|{input_data.trip_duration_days}|{input_data.start_date}|{json.dumps(input_data.hints, sort_keys=True)}"
        
        if cache_key in self._cache and not force:
            cached = self._cache[cache_key]
            agent_data.update(cached.dict())
            state["agent_data"] = agent_data
            return state

        # Prepare LLM call
        payload = {
            "preferences_summary": input_data.preferences_summary.dict(),
            "destination": input_data.destination,
            "activity_catalog": [a.dict() for a in input_data.activity_catalog],
            "trip_duration_days": input_data.trip_duration_days,
            "start_date": input_data.start_date,
            "hints": input_data.hints,
        }

        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM),
            ("user", "Input:\n{payload}\n\nReturn JSON only."),
        ])

        if self.llm is None:
            if self._llm_unavailable_reason:
                print(f"[{AGENT_LABEL}] LLM unavailable: {self._llm_unavailable_reason}")
            out = ItineraryOut(
                itinerary=[],
                insights=["LLM is not available to generate itinerary."],
                warnings=["LLM unavailable; no itinerary generated", f"Reason: {self._llm_unavailable_reason}"] if self._llm_unavailable_reason else ["LLM unavailable; no itinerary generated"],
                metrics={"latency_ms": int((time.time() - t0) * 1000)},
                provenance=["llm_unavailable"],
            )
            agent_data.update(out.dict())
            state["agent_data"] = agent_data
            return state

        structured_llm = self.llm.with_structured_output(ItineraryOut)
        run = prompt | structured_llm
        try:
            result: ItineraryOut = run.invoke({"payload": payload})
        except Exception as e:
            err_text = f"{type(e).__name__}: {e}"
            print(f"[{AGENT_LABEL}] LLM invocation failed: {err_text}")
            out = ItineraryOut(
                itinerary=[],
                insights=["LLM failed to generate itinerary. Try adjusting inputs or hints."],
                warnings=["LLM unavailable or failed; no itinerary generated", f"Error: {err_text}"],
                metrics={"latency_ms": int((time.time() - t0) * 1000)},
                provenance=["llm_failed"],
            )
            agent_data.update(out.dict())
            state["agent_data"] = agent_data
            return state

        metrics = dict(result.metrics or {})
        metrics.update({
            "generated_days": len(result.itinerary),
            "total_activities": sum(len(day.items) for day in result.itinerary),
            "latency_ms": int((time.time() - t0) * 1000),
            "trip_id": trip_id,
            "destination": destination,
            "trip_duration_days": trip_duration_days,
        })

        out = ItineraryOut(
            itinerary=result.itinerary or [],
            insights=result.insights or [],
            warnings=warnings + (result.warnings or []),
            metrics=metrics,
            provenance=(result.provenance or []) + ["llm"],
        )

        agent_data.update(out.dict())
        state["agent_data"] = agent_data

        self._cache[cache_key] = out

        state.setdefault("messages", [])
        state["messages"].append(
            AIMessage(
                content=f"[{AGENT_LABEL}] Completed for trip {trip_id}. Generated {len(out.itinerary)} days."
            )
        )
        return state

    # ---- Graph ----
    def _build_graph(self) -> StateGraph:
        g = StateGraph(AgentState)
        g.add_node("build_itinerary", self._build_itinerary)
        g.set_entry_point("build_itinerary")
        g.add_edge("build_itinerary", END)
        return g.compile()

    # ---- Public API ----
    def run(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        return self.app.invoke(initial_state)


__all__ = [
    "ItineraryAgent",
    "ItineraryItem",
    "DayItinerary",
    "ItineraryOut",
    "ItineraryGenerationInput",
]