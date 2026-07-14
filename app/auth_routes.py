"""Custom registration endpoint that includes the user's display name."""

from pydantic import BaseModel, EmailStr, Field

from fastapi import APIRouter, Depends, HTTPException
from fast_auth import FastAuth, UserAlreadyExists, UserProtocol

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    """Registration payload with email, password, display name, and optional bio."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    bio: str | None = Field(default=None, max_length=2000)


class UserResponse(BaseModel):
    """User info returned after registration."""

    id: int | str
    email: str
    name: str
    bio: str | None = None
    profile_image: str | None = None
    is_active: bool
    is_verified: bool

    model_config = {"from_attributes": True}


_auth: FastAuth | None = None


def set_auth(auth_instance: FastAuth) -> None:
    global _auth  # noqa: PLW0603
    _auth = auth_instance


@router.post("/register", status_code=201, response_model=UserResponse)
async def register(body: RegisterRequest) -> UserResponse:
    """Register a new user with a display name.

    This replaces the built-in ``/auth/register`` from fast-auth so we can
    capture the ``name`` field and store it on the extended User model.
    """
    if _auth is None:
        raise RuntimeError("Auth not initialised")

    hashed = _auth.hasher.hash(body.password)

    try:
        user = await _auth.repo.create(
            email=body.email,
            hashed_password=hashed,
            extra={"name": body.name, "bio": body.bio},
        )
    except UserAlreadyExists:
        raise HTTPException(status_code=409, detail="Email already registered")

    return UserResponse(
        id=user.id,
        email=user.email,
        name=getattr(user, "name", ""),
        bio=getattr(user, "bio", None),
        profile_image=getattr(user, "profile_image", None),
        is_active=user.is_active,
        is_verified=user.is_verified,
    )