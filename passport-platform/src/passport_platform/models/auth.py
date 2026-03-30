from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class TempToken:
    id: int
    user_id: int
    token_hash: str
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime


@dataclass(slots=True)
class ExtensionSession:
    id: int
    user_id: int
    session_token_hash: str
    revoked_at: datetime | None
    created_at: datetime
