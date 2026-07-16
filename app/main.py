"""Chat API — FastAPI + fast-auth + WebSocket."""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fast_auth import FastAuth, FastAuthConfig
from fast_auth.adapters import SQLAUserRepository
from fast_auth.dependencies import register_auth_error_handler

from app.auth_routes import router as auth_custom_router
from app.auth_routes import set_auth as set_auth_routes_auth
from app.chat import router as chat_router
from app.chat import set_auth as set_chat_auth
from app.config import settings
from app.database import async_session_factory, init_db
from app.models import User
from app.profile_routes import router as profile_router
from app.profile_routes import set_auth as set_profile_auth
from app.private_chat import router as private_router
from app.private_chat import set_auth as set_private_auth
from pathlib import Path

# ---------------------------------------------------------------------------
# Push FastAuth env vars so FastAuthConfig picks them up
# ---------------------------------------------------------------------------
for k, v in settings.fastauth_env.items():
    os.environ.setdefault(k, v)

# ---------------------------------------------------------------------------
# FastAuth setup
# ---------------------------------------------------------------------------
auth_config = FastAuthConfig()

repo = SQLAUserRepository(
    session_factory=async_session_factory,
    model=User,
)

auth = FastAuth(
    repo=repo,
    config=auth_config,
)

# Wire auth into sub-modules
set_auth_routes_auth(auth)
set_chat_auth(auth)
set_profile_auth(auth)
set_private_auth(auth)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Chat API",
    version="1.0.0",
    description="Simple WebSocket chat API with JWT authentication (fast-auth).",
)

# Register fast-auth exception handlers (required for proper error responses)
register_auth_error_handler(app)

# Include fast-auth built-in routes EXCEPT /register (we have a custom one)
_SKIP_PATHS = {"/auth/register"}
for route in auth.router.routes:
    path = getattr(route, "path", "")
    if path not in _SKIP_PATHS:
        app.routes.append(route)  # type: ignore[arg-type]

# Mount our custom register endpoint (includes the name field)
app.include_router(auth_custom_router)

# Mount WebSocket chat router
app.include_router(chat_router)

# Mount profile routes
app.include_router(profile_router)

# Mount private chat routes (REST + WebSocket)
app.include_router(private_router)

# Serve uploaded profile images as static files
_UPLOADS = Path(__file__).resolve().parent.parent / "uploads"
_UPLOADS.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS)), name="uploads")


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup() -> None:
    await init_db()


@app.get("/")
async def root() -> dict:
    return {"message": "Chat API is running", "docs": "/docs"}