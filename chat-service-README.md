# chat-service

A real-time chat API built with **FastAPI**, **WebSockets**, and **[fast-auth](https://github.com/Amir-username/fast-auth)**. This is the backend service that powers the [chat-frontend](https://github.com/Amir-username/chat-frontend) React application.

**Live Demo:** [https://chat-frontend-psi-wine.vercel.app/](https://chat-frontend-psi-wine.vercel.app/)

---

## Features

### Authentication (via [fast-auth](https://github.com/Amir-username/fast-auth))
- **Custom Registration** — extended `/auth/register` endpoint that captures display `name` and optional `bio` alongside email and password
- **JSON Login** — `/auth/login/json` returns JWT access and refresh token pair
- **Token Refresh** — `/auth/refresh` issues a new access token using a valid refresh token
- **Logout** — `/auth/logout` revokes both access and refresh tokens server-side
- **Current User** — `/auth/me` returns the authenticated user's info for session hydration
- **JWT Configurable** — secret key, algorithm (HS256), access token TTL (60 min), and refresh token TTL (7 days) are all configurable via environment variables

### Group Chat (WebSocket)
- **Room-Based Messaging** — connect to `/ws/chat/{room_id}?token=<access_token>` to join a room and exchange messages in real time
- **JWT Authentication** — tokens are validated via query parameter; invalid or expired tokens close the socket with code `4001`
- **Connection Manager** — tracks active WebSocket connections per room and broadcasts messages to all participants
- **System Messages** — join and leave events are broadcast as `system`-type messages (e.g., "Alice joined the room")
- **History Replay** — on connect, the server sends the last 200 messages as a `history` message so the client can render the full room context immediately
- **In-Memory Store** — group chat messages are kept in memory (capped at 200) for simplicity — swap for a database in production

### Private (1-on-1) Chat
- **Start a Conversation** — `POST /private/chats` creates a new private chat or returns an existing one between two users
- **List Chats** — `GET /private/chats` returns all private chats for the authenticated user, sorted by most recent, with the last message preview
- **Message History** — `GET /private/chats/{id}` returns the chat details and paginated messages (up to 200 per request)
- **Send Messages** — `POST /private/chats/{id}/messages` persists a message and pushes it in real time via WebSocket if the recipient is online
- **Message Replies** — Telegram-style reply-to support with `reply_to_id`; the API validates the referenced message exists in the same chat
- **Real-Time WebSocket** — `/private/ws/chat/{chat_id}?token=<access_token>` provides instant message delivery with online/offline notifications
- **Persistent Storage** — all private messages are stored in SQLite via SQLAlchemy async ORM

### User Profiles
- **View Profiles** — `GET /auth/me/profile` for own profile, `GET /auth/users/{id}/profile` for any user's public profile
- **Update Profile** — `PATCH /auth/me/profile` to update display name and/or bio
- **Profile Image Upload** — `POST /auth/me/profile-image` accepts image files (jpg, png, gif, webp) up to 5 MB, saved with unique filenames to avoid collisions
- **User Search** — `GET /auth/search?q=...` performs case-insensitive partial name matching, useful for finding users to start private chats with
- **Static File Serving** — uploaded images are served at `/uploads/profile_images/` via FastAPI's `StaticFiles`

### Infrastructure
- **Async Database** — SQLAlchemy async engine with `aiosqlite` for SQLite; tables are auto-created on startup
- **Configuration** — all settings use the `CHAT_` env prefix and can be overridden via a `.env` file (powered by `pydantic-settings`)
- **CORS** — pre-configured for `localhost:3000`, `localhost:5173`, and the production Vercel frontend
- **Auto Docs** — interactive API documentation available at `/docs` (Swagger UI) and `/redoc` (ReDoc)

---

## Tech Stack

| Technology | Purpose |
|---|---|
| [Python](https://www.python.org/) 3.12+ | Runtime |
| [FastAPI](https://fastapi.tiangolo.com/) | Web framework |
| [fast-auth](https://github.com/Amir-username/fast-auth) | JWT authentication library |
| [SQLAlchemy](https://www.sqlalchemy.org/) (async) | ORM |
| [aiosqlite](https://aiosqlite.omnilib.dev/) | Async SQLite driver |
| [WebSockets](https://websockets.readthedocs.io/) | Real-time communication |
| [Pydantic](https://docs.pydantic.dev/) | Request/response validation |
| [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | Environment-based configuration |

---

## Frontend

This backend is designed to work with the [chat-frontend](https://github.com/Amir-username/chat-frontend) React application. The frontend provides the user interface for all features exposed by this API.

---

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** (recommended Python package manager)

---

## Install & Run

```bash
# Clone the repository
git clone https://github.com/Amir-username/chat-service.git
cd chat-service

# Install dependencies
uv sync

# Start the server (with hot reload)
uv run uvicorn app.main:app --reload --port 8000
```

The API will be available at [http://localhost:8000](http://localhost:8000).

- Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Configuration

All settings can be overridden via environment variables (prefixed with `CHAT_`) or a `.env` file in the project root.

| Variable | Default | Description |
|---|---|---|
| `CHAT_DATABASE_URL` | `sqlite+aiosqlite:///chat.db` | Database connection string |
| `CHAT_FASTAUTH_SECRET_KEY` | `dev-secret-key-change-in-production` | JWT signing secret — **change in production** |
| `CHAT_FASTAUTH_ALGORITHM` | `HS256` | JWT signing algorithm |
| `CHAT_FASTAUTH_ACCESS_TOKEN_TTL_MINUTES` | `60` | Access token lifetime in minutes |
| `CHAT_FASTAUTH_REFRESH_TOKEN_TTL_DAYS` | `7` | Refresh token lifetime in days |

Example `.env` file:

```env
CHAT_FASTAUTH_SECRET_KEY=your-production-secret-here
CHAT_DATABASE_URL=sqlite+aiosqlite:///chat.db
```

---

## API Reference

### Authentication

| Endpoint | Method | Description |
|---|---|---|
| `/auth/register` | POST | Register with email, password, name, and optional bio |
| `/auth/login/json` | POST | Login with email and password, returns JWT tokens |
| `/auth/refresh` | POST | Refresh an expired access token |
| `/auth/logout` | POST | Revoke access and refresh tokens |
| `/auth/me` | GET | Get the current authenticated user |

### Profiles

| Endpoint | Method | Description |
|---|---|---|
| `/auth/me/profile` | GET | Get own full profile |
| `/auth/me/profile` | PATCH | Update name and/or bio |
| `/auth/me/profile-image` | POST | Upload or replace profile image |
| `/auth/users/{id}/profile` | GET | Get any user's public profile |
| `/auth/search?q=...` | GET | Search users by name |

### Group Chat (WebSocket)

| Endpoint | Protocol | Description |
|---|---|---|
| `/ws/chat/{room_id}?token=...` | WebSocket | Real-time group chat with history replay |

**Client sends:**
```json
{"content": "hello world"}
```

**Server broadcasts:**
```json
{
  "type": "message",
  "user_id": 1,
  "name": "Alice",
  "content": "hello world",
  "timestamp": "2025-07-05T12:00:00+00:00"
}
```

**On connect, server sends history:**
```json
{
  "type": "history",
  "messages": [...]
}
```

### Private Chat

| Endpoint | Method | Description |
|---|---|---|
| `/private/chats` | POST | Start (or retrieve existing) a private chat |
| `/private/chats` | GET | List all private chats with last message preview |
| `/private/chats/{id}` | GET | Get chat details and paginated messages |
| `/private/chats/{id}/messages` | POST | Send a message (also pushes via WebSocket) |
| `/private/ws/chat/{id}?token=...` | WebSocket | Real-time private chat |

**Send message with reply:**
```json
{"content": "that's a great point", "reply_to_id": 5}
```

---

## Database Models

### User
Extends `BaseUser` from fast-auth with additional profile fields.

| Field | Type | Description |
|---|---|---|
| `id` | Integer (PK) | Auto-increment primary key |
| `email` | String | Unique email address |
| `name` | String(255) | Display name |
| `bio` | Text (nullable) | User biography |
| `profile_image` | String(500, nullable) | Path to uploaded image |

### PrivateChat
Represents a 1-on-1 conversation between two users.

| Field | Type | Description |
|---|---|---|
| `id` | Integer (PK) | Auto-increment primary key |
| `user1_id` | Integer (FK) | First participant |
| `user2_id` | Integer (FK) | Second participant |
| `created_at` | DateTime (UTC) | Chat creation timestamp |

### PrivateMessage
A single message inside a private chat.

| Field | Type | Description |
|---|---|---|
| `id` | Integer (PK) | Auto-increment primary key |
| `chat_id` | Integer (FK) | Parent chat |
| `sender_id` | Integer (FK) | Message author |
| `content` | Text | Message body |
| `reply_to_id` | Integer (FK, nullable) | Replied-to message |
| `created_at` | DateTime (UTC) | Message timestamp |

---

## Project Structure

```
chat-service/
├── app/
│   ├── main.py           # FastAPI app, CORS, router mounting, startup
│   ├── config.py         # pydantic-settings configuration
│   ├── database.py       # async SQLAlchemy engine + session factory
│   ├── models.py         # User, PrivateChat, PrivateMessage ORM models
│   ├── auth_routes.py    # custom /auth/register with name + bio
│   ├── chat.py           # group chat WebSocket endpoint + ConnectionManager
│   ├── profile_routes.py # profile CRUD + image upload + user search
│   └── private_chat.py   # private chat REST + WebSocket endpoints
├── uploads/              # uploaded profile images (auto-created)
├── pyproject.toml        # project metadata and dependencies
└── .env                  # environment variables (not committed)
```

---

## How It Works

### Authentication Flow

1. A user registers via `POST /auth/register` with email, password, name, and optional bio
2. The password is hashed by fast-auth's hasher and stored in the database
3. The user logs in via `POST /auth/login/json` and receives an access token (JWT) and a refresh token
4. The access token is sent in the `Authorization: Bearer <token>` header for REST endpoints
5. For WebSocket connections, the token is passed as a query parameter: `?token=<access_token>`
6. When the access token expires, the frontend calls `POST /auth/refresh` to get a new pair
7. Logout revokes both tokens server-side

### Group Chat Flow

1. The frontend connects to `/ws/chat/{room_id}?token=<access_token>`
2. The server validates the JWT, looks up the user's name, and accepts the connection
3. A `system` message is broadcast to other room members announcing the join
4. The server sends the last 200 messages as a `history` payload to the new connection
5. When a message is received, it is stored in memory, broadcast to all room members, and capped at 200 messages
6. On disconnect, a `system` message announces the departure

### Private Chat Flow

1. User A sends `POST /private/chats` with `user_id` of User B
2. The server checks if a chat already exists between them; if not, it creates one
3. Both users connect to `/private/ws/chat/{chat_id}?token=<access_token>` for real-time messaging
4. Messages can be sent via REST (`POST /private/chats/{id}/messages`) or WebSocket
5. Messages support `reply_to_id` for threading (validated against the same chat)
6. Online/offline status notifications are sent between participants

---

## License

ISC