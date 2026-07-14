from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from fast_auth.adapters.sqlalchemy import BaseUser


class User(BaseUser):
    """Extended user model with name, profile image, and biography."""

    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    profile_image: Mapped[str | None] = mapped_column(
        String(500), nullable=True, default=None
    )