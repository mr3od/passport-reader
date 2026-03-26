from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from passport_platform.db import Database
from passport_platform.enums import ExternalProvider, UserStatus
from passport_platform.errors import (
    InvalidExtensionSessionError,
    InvalidTempTokenError,
    UserBlockedError,
)
from passport_platform.repositories.auth_tokens import AuthTokensRepository
from passport_platform.repositories.users import UsersRepository
from passport_platform.schemas.commands import EnsureUserCommand
from passport_platform.services.auth import AuthService
from passport_platform.services.users import UserService


def test_issue_temp_token_persists_hashed_record(tmp_path) -> None:
    service, user = build_auth_service(tmp_path)

    issued = service.issue_temp_token(user.id)

    assert issued.token
    assert issued.expires_at > issued.record.created_at
    assert issued.record.token_hash != issued.token
    stored = service.auth_tokens.get_temp_token_by_id(issued.record.id)
    assert stored is not None
    assert stored.token_hash == issued.record.token_hash
    assert stored.used_at is None


def test_exchange_temp_token_marks_it_used_and_returns_session(tmp_path) -> None:
    service, user = build_auth_service(tmp_path)
    issued = service.issue_temp_token(user.id)

    session = service.exchange_temp_token(issued.token)

    assert session.session_token
    assert session.authenticated.user.id == user.id
    assert session.expires_at == session.authenticated.session.expires_at
    stored_token = service.auth_tokens.get_temp_token_by_id(issued.record.id)
    assert stored_token is not None
    assert stored_token.used_at is not None


def test_exchange_rejects_used_temp_token(tmp_path) -> None:
    service, user = build_auth_service(tmp_path)
    issued = service.issue_temp_token(user.id)
    service.exchange_temp_token(issued.token)

    with pytest.raises(InvalidTempTokenError) as exc_info:
        service.exchange_temp_token(issued.token)
    assert "استخدام" in str(exc_info.value)


def test_exchange_rejects_expired_temp_token(tmp_path) -> None:
    service, user = build_auth_service(tmp_path)
    issued = service.issue_temp_token(user.id, now=datetime(2026, 3, 13, 10, 0, tzinfo=UTC))

    with pytest.raises(InvalidTempTokenError) as exc_info:
        service.exchange_temp_token(
            issued.token,
            now=datetime(2026, 3, 13, 10, 11, tzinfo=UTC),
        )
    assert "صلاحية" in str(exc_info.value)


def test_authenticate_session_accepts_active_session(tmp_path) -> None:
    service, user = build_auth_service(tmp_path)
    issued = service.issue_temp_token(user.id)
    session = service.exchange_temp_token(issued.token)

    authenticated = service.authenticate_session(session.session_token)

    assert authenticated.user.id == user.id
    assert authenticated.session.id == session.authenticated.session.id


def test_authenticate_session_rejects_revoked_session(tmp_path) -> None:
    service, user = build_auth_service(tmp_path)
    issued = service.issue_temp_token(user.id)
    session = service.exchange_temp_token(issued.token)
    service.revoke_session(session.session_token)

    with pytest.raises(InvalidExtensionSessionError) as exc_info:
        service.authenticate_session(session.session_token)
    assert "إيقاف" in str(exc_info.value)


def test_authenticate_session_rejects_expired_session(tmp_path) -> None:
    service, user = build_auth_service(tmp_path)
    issued = service.issue_temp_token(user.id, now=datetime(2026, 3, 13, 10, 0, tzinfo=UTC))
    session = service.exchange_temp_token(
        issued.token,
        now=datetime(2026, 3, 13, 10, 1, tzinfo=UTC),
    )

    with pytest.raises(InvalidExtensionSessionError) as exc_info:
        service.authenticate_session(
            session.session_token,
            now=datetime(2026, 3, 13, 22, 2, tzinfo=UTC),
        )
    assert "انتهت الجلسة" in str(exc_info.value)


def test_authenticate_session_rejects_blocked_user(tmp_path) -> None:
    service, user = build_auth_service(tmp_path)
    issued = service.issue_temp_token(user.id)
    session = service.exchange_temp_token(issued.token)
    service.users.change_status(user.id, UserStatus.BLOCKED)

    with pytest.raises(UserBlockedError):
        service.authenticate_session(session.session_token)


def build_auth_service(tmp_path):
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    service = AuthService(
        AuthTokensRepository(db),
        users,
        temp_token_ttl=timedelta(minutes=10),
        extension_session_ttl=timedelta(hours=12),
    )
    return service, user
