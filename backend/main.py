import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.system import router as system_router
from api.auth import router as auth_router
from database import test_connection, close_database_connection, init_indexes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Test database connection
    print("🚀 Starting up Travel Planer API...")
    await test_connection()
    await init_indexes()
    yield
    # Shutdown: Close database connection
    print("🛑 Shutting down Travel Planer API...")
    await close_database_connection()


app = FastAPI(title="Travel Planer API", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3060"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(system_router)
app.include_router(auth_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8060)