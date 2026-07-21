"""Private (1-on-1) chat — REST endpoints + real-time WebSocket."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field

from fast_auth import FastAuth, TokenExpired, TokenInvalid, TokenRevoked
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import async_session_factory
from app.models import PrivateChat, PrivateMessage, User

router = APIRouter(prefix="/private", tags=["private-chat"])

_auth: FastAuth | None = None


def set_auth(auth_instance: FastAuth) -> None:
    global _auth  # noqa: PLW0603
    _auth = auth_instance


# ---------------------------------------------------------------------------
# WebSocket connection manager for private chats
# ---------------------------------------------------------------------------
class PrivateChatManager:
    """Manages WebSocket connections per private chat room.

    Layout:  chat_id -> { user_id: websocket }
    """

    def __init__(self) -> None:
        self._rooms: dict[int, dict[int, WebSocket]] = defaultdict(dict)

    def connect(self, ws: WebSocket, chat_id: int, user_id: int) -> None:
        self._rooms[chat_id][user_id] = ws

    def disconnect(self, chat_id: int, user_id: int) -> None:
        room = self._rooms.get(chat_id)
        if room:
            room.pop(user_id, None)
            if not room:
                del self._rooms[chat_id]

    async def send_to_user(
        self, chat_id: int, user_id: int, message: dict
    ) -> bool:
        """Send a message to a specific user in a chat. Returns False if offline."""
        ws = self._rooms.get(chat_id, {}).get(user_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            self.disconnect(chat_id, user_id)
            return False

    async def broadcast(self, chat_id: int, message: dict) -> None:
        """Send to ALL connected users in the chat (both sender + receiver)."""
        dead: list[int] = []
        for uid, ws in self._rooms.get(chat_id, {}).items():
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.disconnect(chat_id, uid)


ws_manager = PrivateChatManager()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
async def _get_user(request: Request) -> User:
    """Extract JWT from Authorization header, return the User ORM object."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth_header[7:]
    try:
        claims = _auth.token_service.decode(token, expected_type="access")
    except (TokenInvalid, TokenExpired, TokenRevoked) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user = await _auth.repo.get_by_id(int(claims["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def _ws_authenticate(token: str) -> User:
    """Validate a WebSocket JWT and return the User ORM object."""
    try:
        claims = _auth.token_service.decode(token, expected_type="access")
    except (TokenInvalid, TokenExpired, TokenRevoked):
        return None  # type: ignore[return-value]
    user = await _auth.repo.get_by_id(int(claims["sub"]))
    return user


async def _ws_get_user_name(user_id: int) -> str:
    """Look up display name from DB."""
    user = await _auth.repo.get_by_id(user_id)
    if user is None:
        return str(user_id)
    return getattr(user, "name", user.email)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
async def _find_existing_chat(session: AsyncSession, user_a: int, user_b: int) -> PrivateChat | None:
    """Find an existing private chat between two users (either order)."""
    stmt = select(PrivateChat).where(
        ((PrivateChat.user1_id == user_a) & (PrivateChat.user2_id == user_b))
        | ((PrivateChat.user1_id == user_b) & (PrivateChat.user2_id == user_a))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_chat_with_access(
    session: AsyncSession, chat_id: int, user_id: int
) -> PrivateChat:
    """Fetch a private chat and verify the requesting user is a participant."""
    chat = await session.get(PrivateChat, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat.user1_id != user_id and chat.user2_id != user_id:
        raise HTTPException(status_code=403, detail="Not a participant in this chat")
    return chat


def _other_user(chat: PrivateChat, my_id: int) -> User:
    """Return the other participant in the chat."""
    return chat.user1 if chat.user1_id != my_id else chat.user2


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class StartChatRequest(BaseModel):
    user_id: int = Field(..., description="The user to start a private chat with")


class ChatListItem(BaseModel):
    id: int
    other_user_id: int
    other_user_name: str
    other_user_image: str | None = None
    last_message: str | None = None
    last_message_at: str | None = None
    created_at: str

    model_config = {"from_attributes": True}


class ChatDetailResponse(BaseModel):
    id: int
    user1_id: int
    user2_id: int
    created_at: str


class ReplyPreview(BaseModel):
    """Snippet of the message being replied to (Telegram-style)."""
    id: int
    sender_id: int
    sender_name: str
    content: str
    created_at: str


class MessageResponse(BaseModel):
    id: int
    chat_id: int
    sender_id: int
    sender_name: str
    content: str
    reply_to: ReplyPreview | None = None
    created_at: str

    model_config = {"from_attributes": True}


class ChatWithMessagesResponse(BaseModel):
    chat: ChatDetailResponse
    messages: list[MessageResponse]
    other_user_id: int
    other_user_name: str
    other_user_image: str | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    reply_to_id: int | None = Field(default=None, description="ID of the message to reply to")


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------
def _fmt_chat_item(chat: PrivateChat, my_id: int) -> dict:
    other = _other_user(chat, my_id)
    last_msg = chat.messages[-1] if chat.messages else None
    return {
        "id": chat.id,
        "other_user_id": other.id,
        "other_user_name": getattr(other, "name", other.email),
        "other_user_image": getattr(other, "profile_image", None),
        "last_message": last_msg.content if last_msg else None,
        "last_message_at": last_msg.created_at.isoformat() if last_msg else None,
        "created_at": chat.created_at.isoformat(),
    }


def _fmt_message(msg: PrivateMessage) -> dict:
    d: dict = {
        "id": msg.id,
        "chat_id": msg.chat_id,
        "sender_id": msg.sender_id,
        "sender_name": getattr(msg.sender, "name", msg.sender.email),
        "content": msg.content,
        "created_at": msg.created_at.isoformat(),
    }
    if msg.reply_to is not None:
        d["reply_to"] = {
            "id": msg.reply_to.id,
            "sender_id": msg.reply_to.sender_id,
            "sender_name": getattr(msg.reply_to.sender, "name", msg.reply_to.sender.email),
            "content": msg.reply_to.content,
            "created_at": msg.reply_to.created_at.isoformat(),
        }
    else:
        d["reply_to"] = None
    return d


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@router.post("/chats", status_code=201, response_model=ChatDetailResponse)
async def start_chat(body: StartChatRequest, request: Request) -> ChatDetailResponse:
    """Start a private chat with another user.

    If a chat already exists between the two users, returns it instead.
    """
    me = await _get_user(request)

    if body.user_id == me.id:
        raise HTTPException(status_code=400, detail="Cannot chat with yourself")

    other = await _auth.repo.get_by_id(body.user_id)
    if other is None:
        raise HTTPException(status_code=404, detail="User not found")

    async with async_session_factory() as session:
        existing = await _find_existing_chat(session, me.id, body.user_id)
        if existing:
            return ChatDetailResponse(
                id=existing.id,
                user1_id=existing.user1_id,
                user2_id=existing.user2_id,
                created_at=existing.created_at.isoformat(),
            )

        chat = PrivateChat(user1_id=me.id, user2_id=body.user_id)
        session.add(chat)
        await session.commit()
        await session.refresh(chat)

    return ChatDetailResponse(
        id=chat.id,
        user1_id=chat.user1_id,
        user2_id=chat.user2_id,
        created_at=chat.created_at.isoformat(),
    )


@router.get("/chats", response_model=list[ChatListItem])
async def list_my_chats(request: Request) -> list[ChatListItem]:
    """List all private chats for the authenticated user, sorted by most recent."""
    me = await _get_user(request)

    async with async_session_factory() as session:
        stmt = (
            select(PrivateChat)
            .where(
                (PrivateChat.user1_id == me.id) | (PrivateChat.user2_id == me.id)
            )
            .order_by(desc(PrivateChat.created_at))
        )
        result = await session.execute(stmt)
        chats = result.scalars().all()

    return [ChatListItem(**_fmt_chat_item(c, me.id)) for c in chats]


@router.get("/chats/{chat_id}", response_model=ChatWithMessagesResponse)
async def get_chat_messages(
    chat_id: int,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> ChatWithMessagesResponse:
    """Get a private chat's details and its messages (paginated, newest first)."""
    me = await _get_user(request)

    async with async_session_factory() as session:
        chat = await _get_chat_with_access(session, chat_id, me.id)

        # Load messages (newest first for the query, we reverse for the response)
        msg_stmt = (
            select(PrivateMessage)
            .where(PrivateMessage.chat_id == chat_id)
            .options(joinedload(PrivateMessage.reply_to).joinedload(PrivateMessage.sender))
            .order_by(desc(PrivateMessage.created_at))
            .offset(offset)
            .limit(limit)
        )
        msg_result = await session.execute(msg_stmt)
        msgs = list(reversed(msg_result.scalars().all()))

    other = _other_user(chat, me.id)
    return ChatWithMessagesResponse(
        chat=ChatDetailResponse(
            id=chat.id,
            user1_id=chat.user1_id,
            user2_id=chat.user2_id,
            created_at=chat.created_at.isoformat(),
        ),
        messages=[MessageResponse(**_fmt_message(m)) for m in msgs],
        other_user_id=other.id,
        other_user_name=getattr(other, "name", other.email),
        other_user_image=getattr(other, "profile_image", None),
    )


@router.post("/chats/{chat_id}/messages", status_code=201, response_model=MessageResponse)
async def send_message(
    chat_id: int,
    body: SendMessageRequest,
    request: Request,
) -> MessageResponse:
    """Send a message in a private chat (HTTP). Also pushes via WebSocket if the
    other user is currently connected."""
    me = await _get_user(request)

    async with async_session_factory() as session:
        chat = await _get_chat_with_access(session, chat_id, me.id)

        # Validate reply_to_id if provided
        reply_to_id = body.reply_to_id
        if reply_to_id is not None:
            replied_msg = await session.get(PrivateMessage, reply_to_id)
            if replied_msg is None or replied_msg.chat_id != chat_id:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid reply_to_id: message not found in this chat",
                )

        msg = PrivateMessage(
            chat_id=chat_id,
            sender_id=me.id,
            content=body.content.strip(),
            reply_to_id=reply_to_id,
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        await session.refresh(msg, ["sender", "reply_to"])

    msg_dict = _fmt_message(msg)

    # Push to WebSocket connections if the other user is online
    other_id = chat.user2_id if chat.user1_id == me.id else chat.user1_id
    await ws_manager.send_to_user(chat_id, other_id, {
        "type": "message",
        **msg_dict,
    })

    return MessageResponse(**msg_dict)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@router.websocket("/ws/chat/{chat_id}")
async def private_chat_ws(websocket: WebSocket, chat_id: int) -> None:
    """Real-time private chat WebSocket.

    Connect: ws://host/private/ws/chat/{chat_id}?token=<access_token>

    Client sends:   {"content": "hello"}
                    {"content": "reply", "reply_to_id": 5}
    Client receives: {"type": "message", "id": 1, "chat_id": 1, "sender_id": 2,
                      "sender_name": "Bob", "content": "hello",
                      "reply_to": null,
                      "created_at": "..."}
    """
    # --- authenticate ---
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    user = await _ws_authenticate(token)
    if user is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    # --- verify access to this chat ---
    async with async_session_factory() as session:
        chat = await session.get(PrivateChat, chat_id)
        if chat is None:
            await websocket.close(code=4004, reason="Chat not found")
            return
        if chat.user1_id != user.id and chat.user2_id != user.id:
            await websocket.close(code=4003, reason="Not a participant")
            return

    # --- connect ---
    await websocket.accept()
    ws_manager.connect(websocket, chat_id, user.id)

    # Determine the other user for notifications
    other_id = chat.user2_id if chat.user1_id == user.id else chat.user1_id

    # Send recent history (last 50 messages)
    async with async_session_factory() as session:
        stmt = (
            select(PrivateMessage)
            .where(PrivateMessage.chat_id == chat_id)
            .options(joinedload(PrivateMessage.reply_to).joinedload(PrivateMessage.sender))
            .order_by(desc(PrivateMessage.id))
            .limit(50)
        )
        result = await session.execute(stmt)
        recent = list(reversed(result.scalars().all()))

    if recent:
        await websocket.send_json({
            "type": "history",
            "messages": [_fmt_message(m) for m in recent],
        })

    # Notify the other user
    user_name = getattr(user, "name", user.email)
    await ws_manager.send_to_user(chat_id, other_id, {
        "type": "system",
        "content": f"{user_name} is online",
        "chat_id": chat_id,
    })

    try:
        while True:
            data = await websocket.receive_json()
            content = data.get("content", "").strip()
            if not content:
                continue

            reply_to_id = data.get("reply_to_id")

            # Persist to DB
            async with async_session_factory() as session:
                # Validate reply_to_id if provided
                if reply_to_id is not None:
                    replied_msg = await session.get(PrivateMessage, reply_to_id)
                    if replied_msg is None or replied_msg.chat_id != chat_id:
                        continue  # silently skip invalid replies

                msg = PrivateMessage(
                    chat_id=chat_id,
                    sender_id=user.id,
                    content=content,
                    reply_to_id=reply_to_id,
                )
                session.add(msg)
                await session.commit()
                await session.refresh(msg)
                await session.refresh(msg, ["sender", "reply_to"])

            msg_dict = {
                "type": "message",
                **_fmt_message(msg),
            }

            # Broadcast to both users (sender + receiver)
            await ws_manager.broadcast(chat_id, msg_dict)

    except WebSocketDisconnect:
        ws_manager.disconnect(chat_id, user.id)
        await ws_manager.send_to_user(chat_id, other_id, {
            "type": "system",
            "content": f"{user_name} went offline",
            "chat_id": chat_id,
        })