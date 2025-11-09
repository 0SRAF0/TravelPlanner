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

---

### 🎨 Preference Agent

**File**: `preference_agent.py`  
**Role**: Processes and aggregates user travel preferences  
**Does**:

- Fetches preferences from database
- Creates semantic embeddings (sentence-transformers)
- Aggregates group preferences (vibes, budget, deal breakers)
- Detects conflicts
- Provides semantic search for recommendations

**Output**: `agent_data["preferences_summary"]`

---

### 📦 Shared State

**File**: `agent_state.py`  
**Role**: Common state schema all agents share  
**Contains**:

- `messages`: Conversation history
- `agent_data`: Agent outputs (preferences, itinerary, etc.)
- `agent_scratch`: Agent working memory
- `next_task`, `done`: Workflow control

---

### 🛠️ Tools

**File**: `tools.py`  
**Role**: Reusable functions for agents  
**Includes**:

- `get_all_group_preferences()`: Fetch from database

---

## Data Flow

```
User Request
    ↓
Orchestrator → Preference Agent → Shared State
    ↓                                  ↓
Next Agent ← ← ← ← ← ← ← ← ← ← ← ← ← ←
(itinerary, accommodation, etc.)
```

## Adding New Agents

1. Create agent file in `agents/`
2. Register in `orchestrator_agent.py` WORKERS dict
3. Add routing logic
4. Store output in `agent_data["{your_key}"]`

