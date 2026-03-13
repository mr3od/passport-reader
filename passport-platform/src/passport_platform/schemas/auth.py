from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from passport_platform.models.auth import ExtensionSession, TempToken
from passport_platform.models.user import User


@dataclass(slots=True)
class IssuedTempToken:
    token: str
    expires_at: datetime
    record: TempToken


@dataclass(slots=True)
class AuthenticatedSession:
    user: User
    session: ExtensionSession


@dataclass(slots=True)
class IssuedExtensionSession:
    session_token: str
    expires_at: datetime
    authenticated: AuthenticatedSession
