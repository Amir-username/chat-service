from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from fast_auth.adapters.sqlalchemy import BaseUser


class User(BaseUser):
    """Extended user model with a display name."""

    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), nullable=False)