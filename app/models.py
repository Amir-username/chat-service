from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fast_auth.adapters.sqlalchemy import BaseUser, _Base


class User(BaseUser):
    """Extended user model with name, profile image, and biography."""

    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    profile_image: Mapped[str | None] = mapped_column(
        String(500), nullable=True, default=None
    )


# ---------------------------------------------------------------------------
# Private chat models (same declarative base as User so FKs resolve)
# ---------------------------------------------------------------------------
class PrivateChat(_Base):
    """A one-to-one conversation between two users."""

    __tablename__ = "private_chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user1_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    user2_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user1: Mapped["User"] = relationship("User", foreign_keys=[user1_id], lazy="joined")
    user2: Mapped["User"] = relationship("User", foreign_keys=[user2_id], lazy="joined")
    messages: Mapped[list["PrivateMessage"]] = relationship(
        back_populates="chat", order_by="PrivateMessage.created_at", lazy="selectin"
    )


class PrivateMessage(_Base):
    """A single message inside a private chat."""

    __tablename__ = "private_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("private_chats.id"), nullable=False, index=True
    )
    sender_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    chat: Mapped["PrivateChat"] = relationship(back_populates="messages")
    sender: Mapped["User"] = relationship(foreign_keys=[sender_id], lazy="joined")