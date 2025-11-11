# Agents Overview

## Architecture

Multi-agent system using `LangGraph` for travel planning coordination.

## Agents

### 🎯 Orchestrator Agent

**File**: `orchestrator_agent.py`  
**Role**: Coordinates workflow and routes between agents  
**Does**:

- Decides which agent runs next
- Manages workflow state
- Routes based on completion status

**Relations**:

- Routes to Preference Agent when `preferences_summary` is missing
- Routes to Destination Research Agent when `preferences_summary` exists and `agent_data["destination"]` is set

---

### 🎨 Preference Agent

**File**: `preference_agent.py`  
**Role**: Processes and aggregates user travel preferences  
**Does**:

- Fetches preferences from database
- Creates semantic embeddings (sentence-transformers)
- Aggregates trip preferences (vibes, budget, deal breakers)
- Detects conflicts
- Provides semantic search for recommendations

**Output**: `agent_data["preferences_summary"]`

**Relations**:

- Feeds `preferences_summary` to the Destination Research Agent

---

### 🧭 Destination Research Agent

**File**: `destination_research_agent.py`  
**Role**: Generates a destination-specific activity catalog aligned to group preferences  
**Does**:

- Creates activity options using `preferences_summary` + `agent_data["destination"]`
- Respects optional hints: `radius_km`, `max_items`, `preferred_categories`
- Returns catalog with helpful `insights`, `warnings`, and `metrics`

**Output**: `agent_data["activity_catalog"]`

**Relations**:

- Consumes `preferences_summary` (from Preference Agent) and `agent_data["destination"]`
- Output can be used by itinerary/planning agents downstream

---

### 📦 Shared State

**File**: `agent_state.py`  
**Role**: Common state schema all agents share  
**Contains**:

- `messages`: Conversation history
- `agent_data`: Agent outputs (preferences, itinerary, etc.)
- `agent_scratch`: Agent working memory
- `next_task`, `done`: Workflow control

Note: Task-specific inputs like `destination` and `hints` should be stored under `agent_data`
(e.g., `agent_data["destination"]`, `agent_data["hints"]`) rather than as top-level state fields.

---

### 🛠️ Tools

**File**: `tools.py`  
**Role**: Reusable functions for agents  
**Includes**:

- `get_all_trip_preferences()`: Fetch from database

---

## Data Flow

```
User Request
    ↓
Orchestrator
    ↓
Preference Agent → Destination Research Agent → Shared State
                                  ↓
                           Next Agent (itinerary, accommodation, etc.)
```

## Adding New Agents

1. Create agent file in `agents/`
2. Register in `orchestrator_agent.py` WORKERS dict
3. Add routing logic
4. Store output in `agent_data["{your_key}"]`



