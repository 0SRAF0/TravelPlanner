from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Literal
from pydantic.v1 import BaseModel, Field, validator
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
import time
import json
from datetime import datetime, timedelta

from app.agents.agent_state import AgentState
from app.agents.destination_research_agent import Activity, PreferencesSummaryIn
from app.core.config import OPEN_AI_MODEL, OPEN_AI_API_KEY


AGENT_LABEL = "itinerary"


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
    start_date: Optional[str] = Field(
        default=None, description="Optional start date for the trip (YYYY-MM-DD)"
    )
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
        api_key = OPEN_AI_API_KEY
        self.llm = None
        self._llm_unavailable_reason: str = ""
        if api_key:
            try:
                self.llm = ChatOpenAI(
                    model=OPEN_AI_MODEL, 
                    temperature=0.7, 
                    api_key=api_key,
                    max_retries=0  # Disable LangChain's retry - we handle it in the agent
                )
            except Exception:
                self.llm = None
                import traceback

                self._llm_unavailable_reason = "Failed to initialize OpenAI client"
                try:
                    self._llm_unavailable_reason += f": {traceback.format_exc(limit=1).strip()}"
                except Exception:
                    pass
        else:
            self._llm_unavailable_reason = "No API key found in OPEN_AI_API_KEY"
        self.app = self._build_graph()

    # ---- Node ----
    async def _build_itinerary(self, state: AgentState) -> AgentState:
        t0 = time.time()
        agent_data = dict(state.get("agent_data", {}) or {})
        
        # Get broadcast callback if available
        broadcast = state.get("broadcast_callback")

        print("\n" + "=" * 80)
        print("  ITINERARY AGENT START")
        print("=" * 80)
        print(f"[PERF] Start timestamp: {time.time()}")
        
        # Broadcast starting status
        if broadcast:
            await broadcast("Itinerary Agent", "running", "Loading activity catalog", progress={"current": 1, "total": 3})

        hints = state.get("hints") or agent_data.get("hints") or {}
        force = bool((hints or {}).get("force", False))
        if agent_data.get("itinerary") and not force:
            print(f"[DEBUG] Itinerary already exists, short-circuiting")
            if broadcast:
                await broadcast("Itinerary Agent", "completed", "Itinerary already exists", progress={"current": 3, "total": 3})
            return state

        # Flexible input locations: top-level or agent_data
        pref_summary = state.get("preferences_summary") or agent_data.get("preferences_summary")
        destination = state.get("destination") or agent_data.get("destination")
        activity_catalog = state.get("activity_catalog") or agent_data.get("activity_catalog")
        trip_duration_days = state.get("trip_duration_days") or agent_data.get(
            "trip_duration_days", 3
        )
        start_date = state.get("start_date") or agent_data.get("start_date")

        # Log input data sizes
        print(f"[DEBUG] Input data sizes:")
        print(f"  - Trip duration: {trip_duration_days} days")
        print(f"  - Activity catalog size: {len(activity_catalog) if activity_catalog else 0} activities")
        print(f"  - Has preferences: {pref_summary is not None}")
        print(f"  - Destination: {destination}")
        print(f"  - Start date: {start_date}")

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
            insights.append(
                "Ensure destination research is performed by the DestinationResearchAgent"
            )

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
                preferences_summary=PreferencesSummaryIn(**pref_summary),  # type: ignore
                destination=destination,  # type: ignore
                activity_catalog=[Activity(**a) for a in activity_catalog],  # type: ignore
                trip_duration_days=trip_duration_days,  # type: ignore
                start_date=start_date,  # type: ignore
                hints=hints,
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

        # Broadcast matching status
        if broadcast:
            activity_count = len(input_data.activity_catalog) if input_data.activity_catalog else 0
            await broadcast("Itinerary Agent", "running", f"Matching {activity_count} activities to preferences", progress={"current": 2, "total": 3})
        
        # Prepare LLM call
        payload_start = time.time()
        print(f"[PROCESSING] Preparing itinerary generation payload...")
        payload = {
            "preferences_summary": input_data.preferences_summary.dict(),
            "destination": input_data.destination,
            "activity_catalog": [a.dict() for a in input_data.activity_catalog],
            "trip_duration_days": input_data.trip_duration_days,
            "start_date": input_data.start_date,
            "hints": input_data.hints,
        }
        payload_latency = (time.time() - payload_start) * 1000
        print(f"[PERF] Payload preparation: {payload_latency:.2f}ms")
        print(f"[DEBUG] Payload sizes:")
        print(f"  - Activities in catalog: {len(payload['activity_catalog'])}")
        print(f"  - Trip duration: {payload['trip_duration_days']} days")

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM),
                ("user", "Input:\n{payload}\n\nReturn JSON only."),
            ]
        )

        if self.llm is None:
            if self._llm_unavailable_reason:
                print(f"[{AGENT_LABEL}] LLM unavailable: {self._llm_unavailable_reason}")
            out = ItineraryOut(
                itinerary=[],
                insights=["LLM is not available to generate itinerary."],
                warnings=[
                    "LLM unavailable; no itinerary generated",
                    f"Reason: {self._llm_unavailable_reason}",
                ]
                if self._llm_unavailable_reason
                else ["LLM unavailable; no itinerary generated"],
                metrics={"latency_ms": int((time.time() - t0) * 1000)},
                provenance=["llm_unavailable"],
            )
            agent_data.update(out.dict())
            state["agent_data"] = agent_data
            return state

        # SINGLE LLM CALL PER TRIP: Generate complete itinerary at once
        # This is the only LLM call in itinerary agent
        structured_llm = self.llm.with_structured_output(ItineraryOut)
        run = prompt | structured_llm
        
        # Retry logic with timing (max 3 attempts = max 3 API calls)
        max_retries = 3
        result: ItineraryOut | None = None
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            api_start = time.time()
            try:
                print(f"[API] Calling OpenAI API for itinerary generation (attempt {attempt}/{max_retries})...")
                result = run.invoke({"payload": payload})
                api_latency = (time.time() - api_start) * 1000
                print(f"[API] ✅ OpenAI API call succeeded")
                print(f"[PERF] API latency: {api_latency:.2f}ms")
                print(f"[PERF] Days generated: {len(result.itinerary)}")
                break  # Success
            except Exception as e:
                api_latency = (time.time() - api_start) * 1000
                last_error = e
                err_text = f"{type(e).__name__}: {e}"
                print(f"[API] ❌ OpenAI API call failed after {api_latency:.2f}ms")
                print(f"[ERROR] Attempt {attempt}/{max_retries}")
                print(f"[ERROR] Error type: {type(e).__name__}")
                print(f"[ERROR] Error message: {str(e)}")
                
                if "quota" in str(e).lower() or "rate" in str(e).lower():
                    print(f"[ERROR] Cause: Rate limit/quota exceeded")
                elif "timeout" in str(e).lower():
                    print(f"[ERROR] Cause: Request timeout")
                
                if attempt < max_retries:
                    retry_delay = 2 ** attempt
                    print(f"[RETRY] Waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                else:
                    print(f"[ERROR] All {max_retries} attempts failed")
        
        if result is None:
            err_text = f"{type(last_error).__name__}: {last_error}" if last_error else "Unknown error"
            print(f"[{AGENT_LABEL}] LLM invocation failed after {max_retries} attempts: {err_text}")
            out = ItineraryOut(
                itinerary=[],
                insights=["LLM failed to generate itinerary. Try adjusting inputs or hints."],
                warnings=[
                    "LLM unavailable or failed; no itinerary generated",
                    f"Error: {err_text}",
                ],
                metrics={"latency_ms": int((time.time() - t0) * 1000)},
                provenance=["llm_failed"],
            )
            agent_data.update(out.dict())
            state["agent_data"] = agent_data
            return state

        # Fallback normalization: if start_date is provided, ensure sequential day dates
        try:
            if input_data.start_date:
                base_date = datetime.fromisoformat(str(input_data.start_date))
                for idx, day in enumerate(result.itinerary or []):
                    expected_date = (base_date + timedelta(days=idx)).date().isoformat()
                    # Always align to expected_date to avoid placeholder dates from LLMs
                    day.date = expected_date
        except Exception as _date_err:
            # Non-fatal: leave dates as produced if normalization fails
            print(f"[{AGENT_LABEL}] Warning: failed to normalize dates: {_date_err}")

        metrics = dict(result.metrics or {})
        total_activities = sum(len(day.items) for day in result.itinerary)
        metrics.update(
            {
                "generated_days": len(result.itinerary),
                "total_activities": total_activities,
                "latency_ms": int((time.time() - t0) * 1000),
                "trip_id": trip_id,
                "destination": destination,
                "trip_duration_days": trip_duration_days,
            }
        )
        
        # Log completion summary
        print("\n" + "=" * 80)
        print("  ITINERARY AGENT COMPLETE")
        print("=" * 80)
        print(f"[RESULT] Trip: {trip_id}")
        print(f"[RESULT] Destination: {destination}")
        print(f"[RESULT] Days generated: {len(result.itinerary)}")
        print(f"[RESULT] Total activities in itinerary: {total_activities}")
        print(f"[RESULT] Activities per day:")
        for idx, day in enumerate(result.itinerary, 1):
            print(f"  - Day {idx}: {len(day.items)} activities")
        
        total_latency = (time.time() - t0) * 1000
        print(f"[PERF] Total itinerary agent latency: {total_latency:.2f}ms ({total_latency/1000:.2f}s)")
        
        # Broadcast completion status
        if broadcast:
            await broadcast("Itinerary Agent", "completed", f"Created {trip_duration_days}-day itinerary with {total_activities} activities", progress={"current": 3, "total": 3})

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
