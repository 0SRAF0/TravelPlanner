from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import APP_NAME, CORS_ORIGINS, SERVER_HOST, SERVER_PORT
from app.db.database import close_database_connection, init_indexes, test_connection
from app.router.activity import router as activity_router
from app.router.auth import router as auth_router
from app.router.trip import router as trip_router
from app.router.perference import router as preference_router
from app.router.system import router as system_router
from app.router.chatbot import router as chat_router
from app.router.location import router as location_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Test database connection
    print("🚀 Starting up Travel Planner API...")
    await test_connection()
    await init_indexes()
    yield
    # Shutdown: Close database connection
    print("🛑 Shutting down Travel Planner API...")
    await close_database_connection()


app = FastAPI(title=APP_NAME, lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(system_router)
app.include_router(auth_router)
app.include_router(trip_router)
app.include_router(preference_router)
app.include_router(activity_router)
app.include_router(chat_router)
app.include_router(location_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
