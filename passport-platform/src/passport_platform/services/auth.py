from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from passport_platform.enums import UserStatus
from passport_platform.errors import (
    InvalidExtensionSessionError,
    InvalidTempTokenError,
    UserBlockedError,
)
from passport_platform.repositories.auth_tokens import AuthTokensRepository
from passport_platform.strings import (
    AUTH_SESSION_EXPIRED,
    AUTH_SESSION_INVALID,
    AUTH_SESSION_REVOKED,
    AUTH_TOKEN_EXPIRED,
    AUTH_TOKEN_INVALID,
    AUTH_TOKEN_USED,
)
from passport_platform.schemas.auth import (
    AuthenticatedSession,
    IssuedExtensionSession,
    IssuedTempToken,
)
from passport_platform.services.users import UserService


class AuthService:
    def __init__(
        self,
        auth_tokens: AuthTokensRepository,
        users: UserService,
        *,
        temp_token_ttl: timedelta = timedelta(minutes=10),
        extension_session_ttl: timedelta = timedelta(hours=12),
    ) -> None:
        self.auth_tokens = auth_tokens
        self.users = users
        self.temp_token_ttl = temp_token_ttl
        self.extension_session_ttl = extension_session_ttl

    def issue_temp_token(self, user_id: int, *, now: datetime | None = None) -> IssuedTempToken:
        issued_at = _utc(now)
        raw_token = secrets.token_urlsafe(24)
        record = self.auth_tokens.create_temp_token(
            user_id=user_id,
            token_hash=_hash_token(raw_token),
            expires_at=issued_at + self.temp_token_ttl,
        )
        return IssuedTempToken(
            token=raw_token,
            expires_at=record.expires_at,
            record=record,
        )

    def exchange_temp_token(
        self,
        raw_token: str,
        *,
        now: datetime | None = None,
    ) -> IssuedExtensionSession:
        current_time = _utc(now)
        token_hash = _hash_token(raw_token)
        session_token = secrets.token_urlsafe(32)
        session_token_hash = _hash_token(session_token)

        with self.auth_tokens.db.transaction(immediate=True) as conn:
            token = self.auth_tokens.get_temp_token_by_hash(token_hash, conn=conn)
            if token is None:
                raise InvalidTempTokenError(AUTH_TOKEN_INVALID)
            if token.used_at is not None:
                raise InvalidTempTokenError(AUTH_TOKEN_USED)
            if token.expires_at <= current_time:
                raise InvalidTempTokenError(AUTH_TOKEN_EXPIRED)

            self.auth_tokens.mark_temp_token_used(token.id, used_at=current_time, conn=conn)
            session = self.auth_tokens.create_extension_session(
                user_id=token.user_id,
                session_token_hash=session_token_hash,
                expires_at=current_time + self.extension_session_ttl,
                conn=conn,
            )

        user = self.users.get_by_id(session.user_id)
        if user is None:
            raise RuntimeError(f"user {session.user_id} not found for extension session")
        if user.status is UserStatus.BLOCKED:
            raise UserBlockedError(user)
        authenticated = AuthenticatedSession(user=user, session=session)
        return IssuedExtensionSession(
            session_token=session_token,
            expires_at=session.expires_at,
            authenticated=authenticated,
        )

    def authenticate_session(
        self,
        raw_session_token: str,
        *,
        now: datetime | None = None,
    ) -> AuthenticatedSession:
        current_time = _utc(now)
        session = self.auth_tokens.get_extension_session_by_hash(_hash_token(raw_session_token))
        if session is None:
            raise InvalidExtensionSessionError(AUTH_SESSION_INVALID)
        if session.revoked_at is not None:
            raise InvalidExtensionSessionError(AUTH_SESSION_REVOKED)
        if session.expires_at <= current_time:
            raise InvalidExtensionSessionError(AUTH_SESSION_EXPIRED)
        user = self.users.get_by_id(session.user_id)
        if user is None:
            raise RuntimeError(f"user {session.user_id} not found for extension session")
        if user.status is UserStatus.BLOCKED:
            raise UserBlockedError(user)
        return AuthenticatedSession(user=user, session=session)

    def issue_dev_session(
        self, user_id: int, *, now: datetime | None = None
    ) -> IssuedExtensionSession:
        current_time = _utc(now)
        session_token = secrets.token_urlsafe(32)
        session_token_hash = _hash_token(session_token)
        session = self.auth_tokens.create_extension_session(
            user_id=user_id,
            session_token_hash=session_token_hash,
            expires_at=current_time + self.extension_session_ttl,
        )
        user = self.users.get_by_id(session.user_id)
        if user is None:
            raise RuntimeError(f"user {session.user_id} not found")
        return IssuedExtensionSession(
            session_token=session_token,
            expires_at=session.expires_at,
            authenticated=AuthenticatedSession(user=user, session=session),
        )

    def revoke_session(
        self,
        raw_session_token: str,
        *,
        now: datetime | None = None,
    ) -> AuthenticatedSession:
        current_time = _utc(now)
        session = self.auth_tokens.get_extension_session_by_hash(_hash_token(raw_session_token))
        if session is None:
            raise InvalidExtensionSessionError(AUTH_SESSION_INVALID)
        updated = self.auth_tokens.revoke_extension_session(session.id, revoked_at=current_time)
        user = self.users.get_by_id(updated.user_id)
        if user is None:
            raise RuntimeError(f"user {updated.user_id} not found for extension session")
        return AuthenticatedSession(user=user, session=updated)


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
