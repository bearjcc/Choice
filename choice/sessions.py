# SPDX-License-Identifier: AGPL-3.0-only
"""In-memory client session registry for the Server Admin panel."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class ClientSession:
    id: str
    user_id: str
    user_agent: str
    created_at: float
    last_seen: float

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user": self.user_id or "",
            "user_agent": self.user_agent,
            "last_seen": self.last_seen,
            "created_at": self.created_at,
        }


class SessionRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, ClientSession] = {}
        self._revoked: set[str] = set()

    def touch(self, session_id: str | None, user_id: str, user_agent: str) -> str:
        now = time.time()
        ua = (user_agent or "")[:512]
        uid = (user_id or "").strip()
        with self._lock:
            if session_id and session_id in self._revoked:
                session_id = None
            if session_id and session_id in self._sessions:
                row = self._sessions[session_id]
                row.last_seen = now
                row.user_id = uid
                row.user_agent = ua or row.user_agent
                return session_id
            sid = secrets.token_urlsafe(18)
            self._sessions[sid] = ClientSession(sid, uid, ua, now, now)
            return sid

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = sorted(self._sessions.values(), key=lambda s: s.last_seen, reverse=True)
            return [row.public() for row in rows]

    def revoke(self, session_id: str) -> bool:
        with self._lock:
            self._revoked.add(session_id)
            return self._sessions.pop(session_id, None) is not None

    def is_revoked(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        with self._lock:
            return session_id in self._revoked
