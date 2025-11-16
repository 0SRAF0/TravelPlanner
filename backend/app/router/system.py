from fastapi import APIRouter

from app.models.common import APIResponse

router = APIRouter(tags=["System"])


@router.get("/", response_model=APIResponse)
def root():
    return APIResponse(
        code=0, msg="ok", data={"msg": "Travel Planner API. Visit /signup or /login."}
    )


@router.get("/health", response_model=APIResponse)
def health_check():
    return APIResponse(
        code=0, msg="ok", data={"status": "healthy", "service": "travel_planner-server"}
    )
