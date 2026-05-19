"""In-memory session tokens (Bearer auth)."""

import secrets
from typing import Any

# token -> {user_id, username, role}
SESSIONS: dict[str, dict[str, Any]] = {}


def create_session(user_id: int, username: str, role: str) -> str:
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {
        "user_id": user_id,
        "username": username,
        "role": role,
    }
    return token


def get_session(token: str) -> dict[str, Any] | None:
    return SESSIONS.get(token)


def revoke_session(token: str) -> None:
    SESSIONS.pop(token, None)
