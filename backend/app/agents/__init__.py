"""
agents package

Intentionally avoid importing submodules at package import time to prevent
side effects (e.g., DB connections) during test collection. Import
specific agents directly, e.g.:

    from app.agents.itinerary_agent import ItineraryAgent
"""

__all__: list[str] = []
