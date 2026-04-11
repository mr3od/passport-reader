from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
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
    def __init__(self) -> None:
        self._archived_at: datetime | None = None

    @staticmethod
    def _base_record():
        return SimpleNamespace(
            upload_id=10,
            user_id=1,
            filename="passport.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://1",
            upload_status=SimpleNamespace(value="processed"),
            created_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
            archived_at=None,
            completed_at=datetime(2026, 3, 13, 10, 1, tzinfo=UTC),
            is_passport=True,
            is_complete=True,
            review_status="auto",
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            confidence_overall=0.91,
            extraction_result={"data": {"PassportNumber": "12345678"}},
            error_code=None,
            masar_status=None,
            masar_detail_id=None,
            submission_entity_id=None,
            submission_entity_type_id=None,
            submission_entity_name=None,
            submission_contract_id=None,
            submission_contract_name=None,
            submission_contract_name_ar=None,
            submission_contract_name_en=None,
            submission_contract_number=None,
            submission_contract_status=None,
            submission_uo_subscription_status_id=None,
            submission_group_id=None,
            submission_group_name=None,
            submission_group_number=None,
            failure_reason_code=None,
            failure_reason_text=None,
        )

    def _record(self):
        record = self._base_record()
        record.archived_at = self._archived_at
        return record

    def list_user_records(self, user_id: int, *, limit: int = 50):
        assert user_id == 1
        return [self._record()]

    def list_user_record_items(self, user_id: int, *, limit: int, offset: int, section: str):
        assert user_id == 1
        assert section in {"pending", "submitted", "failed", "archived", "all"}
        record = self._record()
        if section == "archived" and record.archived_at is None:
            return SimpleNamespace(items=[], total=0, has_more=False)
        item = SimpleNamespace(
            upload_id=record.upload_id,
            filename=record.filename,
            upload_status=record.upload_status,
            review_status=record.review_status,
            masar_status=record.masar_status,
            masar_detail_id=record.masar_detail_id,
            passport_number=record.passport_number,
            full_name_ar="عبد الله العمري",
            full_name_en="ABDULLAH ALOMARI",
            created_at=record.created_at,
            archived_at=record.archived_at,
            completed_at=record.completed_at,
            failure_reason_code=record.failure_reason_code,
            failure_reason_text=record.failure_reason_text,
        )
        return SimpleNamespace(items=[item], total=1, has_more=False)

    def count_user_record_sections(self, user_id: int):
        assert user_id == 1
        return SimpleNamespace(pending=1, submitted=0, failed=0)

    def list_submit_eligible_record_ids(self, user_id: int, *, limit: int, offset: int):
        assert user_id == 1
        item = SimpleNamespace(
            upload_id=10,
            upload_status=SimpleNamespace(value="processed"),
            review_status="auto",
            masar_status=None,
        )
        return SimpleNamespace(items=[item], total=1, has_more=False)

    def get_user_record(self, user_id: int, upload_id: int):
        assert user_id == 1
        if upload_id != 10:
            return None
        return self._record()

    def set_archive_state(self, *, upload_id: int, user_id: int, archived: bool):
        assert user_id == 1
        if upload_id != 10:
            return False
        if archived and self._archived_at is None:
            self._archived_at = datetime(2026, 3, 13, 10, 2, tzinfo=UTC)
        if not archived:
            self._archived_at = None
        return True


def _auth_headers(token: str = "session-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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
    record = client.get("/records/10", headers={"Authorization": "Bearer session-token"})

    assert exchange.status_code == 200
    assert exchange.json() == {"session_token": "session-token"}
    assert me.status_code == 200
    assert me.json()["external_user_id"] == "12345"
    assert records.status_code == 200
    assert records.json()["items"][0]["passport_number"] == "12345678"
    assert record.status_code == 200
    assert record.json()["upload_id"] == 10


def test_records_list_returns_paginated_slim_payload():
    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: ApiServices(
        auth=cast(AuthService, FakeAuthService()),
        records=cast(RecordsService, FakeRecordsService()),
        users=cast(UserService, object()),
    )
    client = TestClient(app)

    response = client.get(
        "/records?section=pending&limit=50&offset=0",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"items", "limit", "offset", "total", "has_more"}
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert payload["total"] == 1
    assert payload["has_more"] is False
    assert payload["items"][0]["passport_number"] == "12345678"
    assert "extraction_result" not in payload["items"][0]
    assert "passport_image_uri" not in payload["items"][0]


def test_records_counts_returns_server_truth():
    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: ApiServices(
        auth=cast(AuthService, FakeAuthService()),
        records=cast(RecordsService, FakeRecordsService()),
        users=cast(UserService, object()),
    )
    client = TestClient(app)

    response = client.get("/records/counts", headers=_auth_headers())

    assert response.status_code == 200
    assert response.json() == {"pending": 1, "submitted": 0, "failed": 0}


def test_records_ids_returns_submit_eligible_rows_only():
    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: ApiServices(
        auth=cast(AuthService, FakeAuthService()),
        records=cast(RecordsService, FakeRecordsService()),
        users=cast(UserService, object()),
    )
    client = TestClient(app)

    response = client.get(
        "/records/ids?section=pending&limit=100&offset=0",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"items", "limit", "offset", "total", "has_more"}
    assert payload["limit"] == 100
    assert payload["offset"] == 0
    assert payload["total"] == 1
    assert payload["has_more"] is False
    assert payload["items"] == [
        {
            "upload_id": 10,
            "upload_status": "processed",
            "review_status": "auto",
            "masar_status": None,
        }
    ]


def test_records_ids_route_is_marked_deprecated_in_openapi():
    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: ApiServices(
        auth=cast(AuthService, FakeAuthService()),
        records=cast(RecordsService, FakeRecordsService()),
        users=cast(UserService, object()),
    )
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    operation = response.json()["paths"]["/records/ids"]["get"]
    assert operation["deprecated"] is True


def test_records_list_rejects_oversize_limit():
    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: ApiServices(
        auth=cast(AuthService, FakeAuthService()),
        records=cast(RecordsService, FakeRecordsService()),
        users=cast(UserService, object()),
    )
    client = TestClient(app)

    response = client.get(
        "/records?section=all&limit=101&offset=0",
        headers=_auth_headers(),
    )

    assert response.status_code == 422


def test_records_list_supports_archived_section():
    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: ApiServices(
        auth=cast(AuthService, FakeAuthService()),
        records=cast(RecordsService, FakeRecordsService()),
        users=cast(UserService, object()),
    )
    client = TestClient(app)

    response = client.get("/records?section=archived&limit=50&offset=0", headers=_auth_headers())

    assert response.status_code == 200
    assert set(response.json().keys()) == {"items", "limit", "offset", "total", "has_more"}


def test_record_detail_still_returns_heavy_fields():
    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: ApiServices(
        auth=cast(AuthService, FakeAuthService()),
        records=cast(RecordsService, FakeRecordsService()),
        users=cast(UserService, object()),
    )
    client = TestClient(app)

    response = client.get("/records/10", headers=_auth_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["upload_id"] == 10
    assert "extraction_result" in payload
    assert "passport_image_uri" in payload


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
    record = client.get(
        f"/records/{upload.id}",
        headers={"Authorization": f"Bearer {session_token}"},
    )

    assert me.status_code == 200
    assert me.json()["external_user_id"] == "12345"
    assert records.status_code == 200
    assert records.json()["total"] == 1
    assert len(records.json()["items"]) == 1
    assert records.json()["items"][0]["passport_number"] == "12345678"
    assert record.status_code == 200
    assert record.json()["upload_id"] == upload.id


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

    submit = client.patch(
        f"/records/{upload.id}/masar-status",
        headers=headers,
        json={
            "status": "submitted",
            "masar_mutamer_id": "M-1",
            "masar_scan_result": {"ok": True},
            "masar_detail_id": "detail-123",
            "submission_entity_id": "819868",
            "submission_entity_type_id": "58",
            "submission_entity_name": "Agency Entity",
            "submission_contract_id": "222452",
            "submission_contract_name": "Contract A",
            "submission_group_id": "group-22",
            "submission_group_name": "Group 22",
            "submission_group_number": "901675540",
        },
    )
    assert submit.status_code == 200
    assert submit.json()["masar_status"] == "submitted"
    assert submit.json()["masar_detail_id"] == "detail-123"
    assert submit.json()["submission_entity_id"] == "819868"
    assert submit.json()["submission_contract_id"] == "222452"
    assert submit.json()["submission_group_id"] == "group-22"


def test_patch_masar_status_accepts_missing_status(tmp_path: Path, monkeypatch):
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
            confidence_overall=0.71,
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
    headers = {"Authorization": f"Bearer {session_token}"}

    submit = client.patch(
        f"/records/{upload.id}/masar-status",
        headers=headers,
        json={
            "status": "missing",
            "submission_entity_id": "819868",
            "submission_entity_type_id": "58",
            "submission_entity_name": "Agency Entity",
            "submission_contract_id": "222452",
            "submission_contract_name": "Contract A",
            "submission_group_id": "group-22",
            "submission_group_name": "Group 22",
            "submission_group_number": "901675540",
            "failure_reason_code": "scan-image-unclear",
            "failure_reason_text": "Passport image is not clear",
        },
    )
    assert submit.status_code == 200
    assert submit.json()["masar_status"] == "missing"
    assert submit.json()["submission_contract_id"] == "222452"
    assert submit.json()["submission_group_id"] == "group-22"
    assert submit.json()["failure_reason_code"] == "scan-image-unclear"
    assert submit.json()["failure_reason_text"] == "Passport image is not clear"


def test_patch_masar_status_rejects_fake_pending_status(tmp_path: Path, monkeypatch):
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
            confidence_overall=0.71,
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
    headers = {"Authorization": f"Bearer {session_token}"}

    response = client.patch(
        f"/records/{upload.id}/masar-status",
        headers=headers,
        json={"status": "pending"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "status must be 'submitted', 'failed', or 'missing'"


def test_patch_archive_status_is_idempotent_and_status_agnostic(tmp_path: Path, monkeypatch):
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
            confidence_overall=0.71,
            extraction_result_json='{"data":{"PassportNumber":"12345678"}}',
            completed_at=datetime(2026, 3, 13, 10, 1, tzinfo=UTC),
        ),
    )
    services.records.update_masar_status(
        upload_id=upload.id,
        user_id=user.id,
        status="submitted",
        masar_mutamer_id="M-1",
        masar_scan_result={"ok": True},
        masar_detail_id="detail-123",
        submission_entity_id="819868",
        submission_entity_type_id="58",
        submission_entity_name="Agency Entity",
        submission_contract_id="222452",
        submission_contract_name="Contract A",
    )
    temp = services.auth.issue_temp_token(user.id)

    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: services
    client = TestClient(app)

    exchange = client.post("/auth/exchange", json={"token": temp.token})
    assert exchange.status_code == 200
    headers = {"Authorization": f"Bearer {exchange.json()['session_token']}"}

    archive_first = client.patch(
        f"/records/{upload.id}/archive",
        headers=headers,
        json={"archived": True},
    )
    archive_second = client.patch(
        f"/records/{upload.id}/archive",
        headers=headers,
        json={"archived": True},
    )
    archived_list = client.get("/records?section=archived", headers=headers)
    submitted_list = client.get("/records?section=submitted", headers=headers)
    unarchive = client.patch(
        f"/records/{upload.id}/archive",
        headers=headers,
        json={"archived": False},
    )
    submitted_after = client.get("/records?section=submitted", headers=headers)

    assert archive_first.status_code == 200
    assert archive_second.status_code == 200
    assert archive_first.json()["archived_at"] is not None
    assert archive_second.json()["archived_at"] == archive_first.json()["archived_at"]
    assert archived_list.status_code == 200
    assert [item["upload_id"] for item in archived_list.json()["items"]] == [upload.id]
    assert submitted_list.status_code == 200
    assert submitted_list.json()["total"] == 0
    assert unarchive.status_code == 200
    assert unarchive.json()["archived_at"] is None
    assert submitted_after.status_code == 200
    assert submitted_after.json()["total"] == 1
