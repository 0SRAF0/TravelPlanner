# AI-Powered Group Travel Planning System

**Enterprise Agentic Platform for Collaborative Trip Coordination**

## How It Works (MVP)

1. Trip creator fills out web form with participant emails and trip constraints
2. Participants receive email link to preference survey (web form)
3. AI agents analyze responses and generate 3-5 destination recommendations
4. Group votes on destinations using ranked-choice voting
5. Winning destination triggers itinerary generation agent
6. System delivers day-by-day plan with booking links

## Core Agents (MVP)

1. **Orchestrator Agent**: Manages workflow state
2. **Preference Analysis Agent**: Extracts patterns from survey responses
3. **Destination Research Agent**: Matches destinations to preferences
4. **Voting Coordinator Agent**: Runs ranked-choice algorithm
5. **Conflict Resolution Agent**: Proposes compromises if no consensus
6. **Itinerary Generation Agent**: Creates detailed day-by-day plans

## Tech Stack (MVP)

- **Backend**: Python FastAPI + MongoDB + Redis
- **Agent Framework**: LangChain + LangGraph
- **LLM**: OpenAI GPT-4
- **Frontend**: React.js
- **Deployment**: Docker Compose on single VM
- **APIs**: Google Maps (routing), Google OAuth (auth), Amadeus (flights) - others mocked
