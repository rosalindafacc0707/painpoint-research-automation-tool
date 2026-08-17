import base64
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from config import BASIC_AUTH_PASSWORD, BASIC_AUTH_USER
from routers.routers import router

app = FastAPI(
    title="Pain-Points Researcher Tool",
    description="FastAPI wrappers around Pain-Points Researcher Tool services.",
    version="0.1.0",
)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Gates the whole app (API + static frontend) behind one shared
    username/password when deployed somewhere reachable by anyone other
    than the developer (e.g. Render). No-ops when BASIC_AUTH_USER is unset,
    so local dev stays exactly as open as before."""

    async def dispatch(self, request: Request, call_next):
        if not BASIC_AUTH_USER or request.url.path == "/health":
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[len("Basic "):]).decode("utf-8")
                user, _, password = decoded.partition(":")
            except (ValueError, UnicodeDecodeError):
                user, password = "", ""
            if secrets.compare_digest(user, BASIC_AUTH_USER) and secrets.compare_digest(
                password, BASIC_AUTH_PASSWORD or ""
            ):
                return await call_next(request)

        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Restricted"'})


app.add_middleware(BasicAuthMiddleware)

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


@app.get("/health")
async def health():
    """Unauthenticated liveness check for Render's health probe."""
    return {"status": "ok"}

# Serve frontend/index.html at "/" so the UI and the API share one origin.
# Mounted after include_router so the /painpoint-researcher/* routes above
# still take precedence over this catch-all.
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
