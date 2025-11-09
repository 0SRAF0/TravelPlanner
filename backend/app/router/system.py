from fastapi import APIRouter


router = APIRouter(tags=["system"])


@router.get("/")
def root():
    return {"msg": "Travel Planer API. Visit /signup or /login."}


@router.get("/health")
def health_check():
    return {"status": "healthy", "service": "travel_planer-server"}


