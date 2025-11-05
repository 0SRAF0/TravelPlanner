import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.system import router as system_router
from api.auth import router as auth_router


app = FastAPI(title="Travel Planer API")

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