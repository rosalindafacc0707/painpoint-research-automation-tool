from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers.routers import router

app = FastAPI(
    title="Pain-Points Researcher Tool",
    description="FastAPI wrappers around Pain-Points Researcher Tool services.",
    version="0.1.0",
)

# Dev-friendly CORS: lets frontend/index.html call the API even when served
# from a different origin (e.g. a separate static file server on another
# port). Not needed when the frontend is served from this same app below.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Serve frontend/index.html at "/" so the UI and the API share one origin.
# Mounted after include_router so the /painpoint-researcher/* routes above
# still take precedence over this catch-all.
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
