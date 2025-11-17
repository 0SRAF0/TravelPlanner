"""
Location Router
Provides location autocomplete using Google Places API
"""

from fastapi import APIRouter, HTTPException, Query
import httpx
from app.core.config import GOOGLE_MAPS_API_KEY
from app.models.common import APIResponse

router = APIRouter(prefix="/locations", tags=["Locations"])


@router.get("/autocomplete", response_model=APIResponse)
async def autocomplete_location(
    input: str = Query(..., description="Search query for location", min_length=2),
):
    """
    Get location autocomplete suggestions from Google Places API

    Args:
        input: Search query (e.g., "Tokyo", "Paris, France")

    Returns:
        List of location suggestions with place_id and formatted descriptions
    """
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Google Maps API key not configured. Please set GOOGLE_MAPS_API_KEY environment variable.",
        )

    try:
        url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
        params = {
            "input": input,
            "types": "(regions)",  # Focus on cities, regions, countries
            "key": GOOGLE_MAPS_API_KEY,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Google Places API error: {response.text}",
                )

            data = response.json()

            if data.get("status") != "OK":
                # Handle specific Google API errors
                if data.get("status") == "ZERO_RESULTS":
                    return APIResponse(code=0, msg="ok", data={"predictions": []})
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Google Places API returned status: {data.get('status')}",
                    )

            return APIResponse(code=0, msg="ok", data={"predictions": data.get("predictions", [])})

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch location suggestions: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching location suggestions: {str(e)}"
        )
