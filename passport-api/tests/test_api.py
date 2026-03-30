from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient
from passport_api.app import create_app
from passport_api.deps import get_api_services
from passport_api.services import ApiServices, build_services
from passport_platform import (
    ChannelName,
    Database,
    ExternalProvider,
    PlanName,
    UserStatus,
)
from passport_platform.models.auth import ExtensionSession
from passport_platform.models.user import User
from passport_platform.repositories import UploadsRepository, UsageRepository, UsersRepository
from passport_platform.schemas.auth import AuthenticatedSession, IssuedExtensionSession
from passport_platform.schemas.commands import (
    EnsureUserCommand,
    RecordProcessingResultCommand,
    RegisterUploadCommand,
)
from passport_platform.services.auth import AuthService
from passport_platform.services.records import RecordsService
from passport_platform.services.uploads import UploadService
from passport_platform.services.users import UserService


class FakeAuthService:
    def exchange_temp_token(self, token: str) -> IssuedExtensionSession:
        assert token == "temp-token"
        return IssuedExtensionSession(
            session_token="session-token",
            authenticated=AuthenticatedSession(
                user=make_fake_user(),
                session=ExtensionSession(
                    id=1,
                    user_id=1,
                    session_token_hash="session-token-hash",
                    revoked_at=None,
                    created_at=datetime(2026, 3, 13, 11, 30, tzinfo=UTC),
                ),
            ),
        )

    def authenticate_session(self, token: str) -> AuthenticatedSession:
        assert token == "session-token"
        return AuthenticatedSession(
            user=make_fake_user(),
            session=ExtensionSession(
                id=1,
                user_id=1,
                session_token_hash="session-token-hash",
                revoked_at=None,
                created_at=datetime(2026, 3, 13, 11, 30, tzinfo=UTC),
            ),
        )


class FakeRecordsService:
    def list_user_records(self, user_id: int, *, limit: int = 50):
        assert user_id == 1
        assert limit == 50
        return [
            type(
                "Record",
                (),
                {
                    "upload_id": 10,
                    "user_id": 1,
                    "filename": "passport.jpg",
                    "mime_type": "image/jpeg",
                    "source_ref": "telegram://1",
                    "upload_status": type("Status", (), {"value": "processed"})(),
                    "created_at": datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
                    "completed_at": datetime(2026, 3, 13, 10, 1, tzinfo=UTC),
                    "is_passport": True,
                    "is_complete": True,
                    "review_status": "auto",
                    "passport_number": "12345678",
                    "passport_image_uri": "/tmp/original.jpg",
                    "confidence_overall": 0.91,
                    "extraction_result": {"data": {"PassportNumber": "12345678"}},
                    "error_code": None,
                    "masar_status": None,
                },
            )()
        ]


def make_fake_user() -> User:
    return User(
        id=1,
        external_provider=ExternalProvider.TELEGRAM,
        external_user_id="12345",
        display_name="Agency A",
        plan=PlanName.FREE,
        status=UserStatus.ACTIVE,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
    )


def test_exchange_me_and_records_endpoints():
    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: ApiServices(
        auth=cast(AuthService, FakeAuthService()),
        records=cast(RecordsService, FakeRecordsService()),
        users=cast(UserService, object()),
    )
    client = TestClient(app)

    exchange = client.post("/auth/exchange", json={"token": "temp-token"})
    me = client.get("/me", headers={"Authorization": "Bearer session-token"})
    records = client.get("/records", headers={"Authorization": "Bearer session-token"})

    assert exchange.status_code == 200
    assert exchange.json() == {"session_token": "session-token"}
    assert me.status_code == 200
    assert me.json()["external_user_id"] == "12345"
    assert records.status_code == 200
    assert records.json()[0]["passport_number"] == "12345678"


def test_health_endpoint_and_debug_mode():
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert app.debug is False
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dev_token_route_is_not_available():
    app = create_app()
    client = TestClient(app)

    response = client.post("/auth/dev-token")

    assert response.status_code == 404


def test_end_to_end_exchange_me_and_records(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "platform.sqlite3"
    monkeypatch.setenv("PASSPORT_PLATFORM_DB_PATH", str(db_path))
    monkeypatch.setenv("PASSPORT_PLATFORM_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    services = build_services()
    db = Database(db_path)
    users = UserService(UsersRepository(db))
    uploads = UploadService(UploadsRepository(db), UsageRepository(db))
    user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    upload = uploads.register_upload(
        RegisterUploadCommand(
            user_id=user.id,
            channel=ChannelName.TELEGRAM,
            filename="passport.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://chat/1/message/2/file/abc",
        )
    )
    uploads.record_processing_result(
        user.id,
        RecordProcessingResultCommand(
            upload_id=upload.id,
            is_passport=True,
            is_complete=True,
            review_status="auto",
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            confidence_overall=0.91,
            extraction_result_json='{"data":{"PassportNumber":"12345678"}}',
            completed_at=datetime(2026, 3, 13, 10, 1, tzinfo=UTC),
        ),
    )
    temp = services.auth.issue_temp_token(user.id)

    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: services
    client = TestClient(app)

    exchange = client.post("/auth/exchange", json={"token": temp.token})
    assert exchange.status_code == 200
    session_token = exchange.json()["session_token"]

    me = client.get("/me", headers={"Authorization": f"Bearer {session_token}"})
    records = client.get("/records", headers={"Authorization": f"Bearer {session_token}"})

    assert me.status_code == 200
    assert me.json()["external_user_id"] == "12345"
    assert records.status_code == 200
    assert len(records.json()) == 1
    assert records.json()[0]["passport_number"] == "12345678"


def test_second_exchange_revokes_first_session_token(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "platform.sqlite3"
    monkeypatch.setenv("PASSPORT_PLATFORM_DB_PATH", str(db_path))
    monkeypatch.setenv("PASSPORT_PLATFORM_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    services = build_services()
    db = Database(db_path)
    users = UserService(UsersRepository(db))
    user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    first_temp = services.auth.issue_temp_token(user.id)
    second_temp = services.auth.issue_temp_token(user.id)

    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: services
    client = TestClient(app)

    first_exchange = client.post("/auth/exchange", json={"token": first_temp.token})
    second_exchange = client.post("/auth/exchange", json={"token": second_temp.token})

    assert first_exchange.status_code == 200
    assert second_exchange.status_code == 200

    first_token = first_exchange.json()["session_token"]
    second_token = second_exchange.json()["session_token"]

    first_me = client.get("/me", headers={"Authorization": f"Bearer {first_token}"})
    second_me = client.get("/me", headers={"Authorization": f"Bearer {second_token}"})

    assert first_me.status_code == 401
    assert second_me.status_code == 200


def test_review_gate_before_masar_submit(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "platform.sqlite3"
    monkeypatch.setenv("PASSPORT_PLATFORM_DB_PATH", str(db_path))
    monkeypatch.setenv("PASSPORT_PLATFORM_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    services = build_services()
    db = Database(db_path)
    users = UserService(UsersRepository(db))
    uploads = UploadService(UploadsRepository(db), UsageRepository(db))
    user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    upload = uploads.register_upload(
        RegisterUploadCommand(
            user_id=user.id,
            channel=ChannelName.TELEGRAM,
            filename="passport.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://chat/1/message/2/file/abc",
        )
    )
    uploads.record_processing_result(
        user.id,
        RecordProcessingResultCommand(
            upload_id=upload.id,
            is_passport=True,
            is_complete=True,
            review_status="needs_review",
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            confidence_overall=0.71,
            extraction_result_json='{"data":{"PassportNumber":"12345678"},"warnings":["requires_review"]}',
            completed_at=datetime(2026, 3, 13, 10, 1, tzinfo=UTC),
        ),
    )
    temp = services.auth.issue_temp_token(user.id)

    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: services
    client = TestClient(app)

    exchange = client.post("/auth/exchange", json={"token": temp.token})
    assert exchange.status_code == 200
    session_token = exchange.json()["session_token"]
    headers = {"Authorization": f"Bearer {session_token}"}

    blocked_submit = client.patch(
        f"/records/{upload.id}/masar-status",
        headers=headers,
        json={
            "status": "submitted",
            "masar_mutamer_id": "M-1",
            "masar_scan_result": {"ok": True},
        },
    )
    assert blocked_submit.status_code == 409

    review = client.patch(
        f"/records/{upload.id}/review-status",
        headers=headers,
        json={"status": "reviewed"},
    )
    assert review.status_code == 200
    assert review.json()["review_status"] == "reviewed"

    submit = client.patch(
        f"/records/{upload.id}/masar-status",
        headers=headers,
        json={
            "status": "submitted",
            "masar_mutamer_id": "M-1",
            "masar_scan_result": {"ok": True},
        },
    )
    assert submit.status_code == 200
    assert submit.json()["masar_status"] == "submitted"
