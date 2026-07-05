"""WebSocket-based chat service with JWT authentication."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from fast_auth import FastAuth, TokenInvalid, TokenExpired, TokenRevoked

router = APIRouter(tags=["chat"])


# ---------------------------------------------------------------------------
# In-memory message store (simple — swap for DB in production)
# ---------------------------------------------------------------------------
messages: list[dict] = []
MAX_HISTORY = 200


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    """Tracks active WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        # room_id -> list of (user_id, name, websocket)
        self._rooms: dict[str, list[tuple]] = defaultdict(list)

    async def connect(
        self, websocket: WebSocket, room_id: str, user_id: int | str, name: str
    ) -> None:
        await websocket.accept()
        self._rooms[room_id].append((user_id, name, websocket))

    def disconnect(
        self, websocket: WebSocket, room_id: str
    ) -> None:
        self._rooms[room_id] = [
            entry for entry in self._rooms[room_id] if entry[2] is not websocket
        ]
        if not self._rooms[room_id]:
            del self._rooms[room_id]

    async def broadcast(
        self, room_id: str, message: dict, exclude: WebSocket | None = None
    ) -> None:
        """Send a message dict to every connection in *room_id* (optionally
        excluding one socket so the sender gets a different ack)."""
        disconnected: list[tuple] = []
        for entry in self._rooms.get(room_id, []):
            _, _, ws = entry
            if ws is exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(entry)
        # Clean up dead sockets
        for entry in disconnected:
            self._rooms[room_id].remove(entry)

    @property
    def active_connections(self) -> int:
        return sum(len(v) for v in self._rooms.values())


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Auth dependency for WebSocket (token via query param)
# ---------------------------------------------------------------------------
_auth: FastAuth | None = None  # set at app startup via set_auth


def set_auth(auth_instance: FastAuth) -> None:
    """Wire the auth instance into the chat module (called from main.py)."""
    global _auth  # noqa: PLW0603
    _auth = auth_instance


async def ws_get_current_user(token: str = Query(...)) -> dict:
    """Validate a JWT passed as a query parameter and return the payload.

    Returns a dict with at least ``sub`` (user id) and ``email``.
    """
    claims = _auth.token_service.decode(token, expected_type="access")
    return claims


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@router.websocket("/ws/chat/{room_id}")
async def chat_websocket(websocket: WebSocket, room_id: str) -> None:
    """Authenticated WebSocket chat endpoint.

    Connect with: ws://host/ws/chat/{room_id}?token=<access_token>

    Messages are JSON objects.  The server expects:
        {"content": "hello world"}

    The server broadcasts to all other clients in the same room:
        {
            "user_id": 1,
            "name": "Alice",
            "content": "hello world",
            "timestamp": "2025-07-05T12:00:00Z"
        }
    """
    # --- authenticate via query param ---
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        claims = await ws_get_current_user(token)
    except (TokenInvalid, TokenExpired, TokenRevoked):
        await websocket.close(code=4001, reason="Invalid or expired token")
        return
    except Exception:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    user_id = claims.get("sub")
    user_email = claims.get("email", "")
    user_name = claims.get("name", user_email)

    # If name wasn't embedded in JWT, look it up from the repo
    if user_name == user_email or not user_name:
        try:
            user_obj = await _auth.repo.get_by_id(int(user_id))
            user_name = getattr(user_obj, "name", user_email)
        except Exception:
            user_name = user_email

    # --- connect ---
    await manager.connect(websocket, room_id, user_id, user_name)

    # Notify everyone that a user joined
    join_msg = {
        "type": "system",
        "content": f"{user_name} joined the room",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast(room_id, join_msg, exclude=websocket)
    # Send chat history to the newly connected user
    if messages:
        await websocket.send_json({"type": "history", "messages": messages})

    try:
        while True:
            data = await websocket.receive_json()

            content = data.get("content", "").strip()
            if not content:
                continue

            now = datetime.now(timezone.utc).isoformat()
            chat_msg = {
                "type": "message",
                "user_id": user_id,
                "name": user_name,
                "content": content,
                "timestamp": now,
            }

            # Persist in memory
            messages.append(chat_msg)
            if len(messages) > MAX_HISTORY:
                del messages[: len(messages) - MAX_HISTORY]

            # Broadcast to everyone in the room (including sender for consistency)
            await manager.broadcast(room_id, chat_msg)

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        leave_msg = {
            "type": "system",
            "content": f"{user_name} left the room",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await manager.broadcast(room_id, leave_msg)