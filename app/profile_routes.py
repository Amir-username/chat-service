"""Profile endpoints — upload image, update bio, view profiles."""

import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    UploadFile,
    File,
)
from pydantic import BaseModel, Field

from fast_auth import TokenInvalid, TokenExpired, UserProtocol

from app.database import async_session_factory

router = APIRouter(prefix="/auth", tags=["profile"])

_auth = None  # set via set_auth from main.py


def set_auth(auth_instance) -> None:
    global _auth  # noqa: PLW0603
    _auth = auth_instance


# ---------------------------------------------------------------------------
# Uploads directory
# ---------------------------------------------------------------------------
_UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads" / "profile_images"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class UpdateProfileRequest(BaseModel):
    """Payload for updating name and/or bio."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    bio: str | None = Field(default=None, max_length=2000)


class ProfileResponse(BaseModel):
    """Full public profile of a user."""

    id: int | str
    email: str
    name: str
    bio: str | None = None
    profile_image: str | None = None
    is_active: bool
    is_verified: bool
    roles: list[str] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Auth helper — resolve current user from Bearer token
# ---------------------------------------------------------------------------
async def _get_current_user(request: Request) -> UserProtocol:
    """Extract the JWT from the Authorization header and return the user."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = auth_header[7:]
    try:
        claims = _auth.token_service.decode(token, expected_type="access")
    except (TokenInvalid, TokenExpired) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user = await _auth.repo.get_by_id(int(claims["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _user_to_profile(user: UserProtocol) -> dict:
    """Convert a User ORM object to a profile dict."""
    return {
        "id": user.id,
        "email": user.email,
        "name": getattr(user, "name", ""),
        "bio": getattr(user, "bio", None),
        "profile_image": getattr(user, "profile_image", None),
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "roles": user.roles,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/me/profile", response_model=ProfileResponse)
async def get_my_profile(request: Request) -> ProfileResponse:
    """Return the authenticated user's full profile."""
    user = await _get_current_user(request)
    fresh = await _auth.repo.get_by_id(user.id)
    if fresh is None:
        raise HTTPException(status_code=404, detail="User not found")
    return ProfileResponse(**_user_to_profile(fresh))


@router.get("/users/{user_id}/profile", response_model=ProfileResponse)
async def get_user_profile(user_id: int) -> ProfileResponse:
    """Return any user's public profile."""
    user = await _auth.repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return ProfileResponse(**_user_to_profile(user))


@router.patch("/me/profile", response_model=ProfileResponse)
async def update_my_profile(
    body: UpdateProfileRequest,
    request: Request,
) -> ProfileResponse:
    """Update the authenticated user's name and/or bio."""
    user = await _get_current_user(request)

    fields = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.bio is not None:
        fields["bio"] = body.bio

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    async with async_session_factory() as session:
        from sqlalchemy import update

        from app.models import User

        stmt = update(User).where(User.id == user.id).values(**fields)
        await session.execute(stmt)
        await session.commit()

    updated = await _auth.repo.get_by_id(user.id)
    return ProfileResponse(**_user_to_profile(updated))


@router.post("/me/profile-image", response_model=ProfileResponse)
async def upload_profile_image(
    request: Request,
    file: UploadFile = File(..., description="Image file (jpg, png, gif, webp, max 5 MB)"),
) -> ProfileResponse:
    """Upload or replace the authenticated user's profile image.

    Returns the updated profile with the new image URL.
    """
    user = await _get_current_user(request)

    # Validate extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5 MB)")

    # Save with a unique name to avoid collisions
    filename = f"{user.id}_{uuid.uuid4().hex}{ext}"
    file_path = _UPLOADS_DIR / filename

    with open(file_path, "wb") as f:
        f.write(content)

    # Build the URL path that clients can use
    image_url = f"/uploads/profile_images/{filename}"

    # Update user in DB
    async with async_session_factory() as session:
        from sqlalchemy import update

        from app.models import User

        stmt = update(User).where(User.id == user.id).values(profile_image=image_url)
        await session.execute(stmt)
        await session.commit()

    updated = await _auth.repo.get_by_id(user.id)
    return ProfileResponse(**_user_to_profile(updated))