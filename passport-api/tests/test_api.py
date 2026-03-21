from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from passport_platform import (
    ChannelName,
    Database,
    ExternalProvider,
)
from passport_platform.repositories import UploadsRepository, UsageRepository, UsersRepository
from passport_platform.schemas.auth import AuthenticatedSession, IssuedExtensionSession
from passport_platform.schemas.commands import (
    EnsureUserCommand,
    RecordProcessingResultCommand,
    RegisterUploadCommand,
)
from passport_platform.services.uploads import UploadService
from passport_platform.services.users import UserService

from passport_api.app import create_app
from passport_api.deps import get_api_services
from passport_api.services import ApiServices, build_services


class FakeAuthService:
    def exchange_temp_token(self, token: str):
        assert token == "temp-token"
        expires_at = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)
        return IssuedExtensionSession(
            session_token="session-token",
            expires_at=expires_at,
            authenticated=AuthenticatedSession(
                user=FakeUser(),
                session=type("Session", (), {"expires_at": expires_at})(),
            ),
        )

    def authenticate_session(self, token: str):
        assert token == "session-token"
        return AuthenticatedSession(
            user=FakeUser(),
            session=type("Session", (), {"id": 1})(),
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
                    "has_face": True,
                    "is_complete": True,
                    "passport_number": "12345678",
                    "passport_image_uri": "/tmp/original.jpg",
                    "face_crop_uri": "/tmp/face.jpg",
                    "core_result": {"data": {"PassportNumber": "12345678"}},
                    "error_code": None,
                    "masar_status": None,
                },
            )()
        ]


class FakeUser:
    id = 1
    display_name = "Agency A"
    external_provider = type("Provider", (), {"value": "telegram"})()
    external_user_id = "12345"
    plan = type("Plan", (), {"value": "free"})()
    status = type("Status", (), {"value": "active"})()


def test_exchange_me_and_records_endpoints():
    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: ApiServices(
        auth=FakeAuthService(),  # type: ignore[arg-type]
        records=FakeRecordsService(),  # type: ignore[arg-type]
        users=None,  # type: ignore[arg-type]
    )
    client = TestClient(app)

    exchange = client.post("/auth/exchange", json={"token": "temp-token"})
    me = client.get("/me", headers={"Authorization": "Bearer session-token"})
    records = client.get("/records", headers={"Authorization": "Bearer session-token"})

    assert exchange.status_code == 200
    assert exchange.json()["session_token"] == "session-token"
    assert me.status_code == 200
    assert me.json()["external_user_id"] == "12345"
    assert records.status_code == 200
    assert records.json()[0]["passport_number"] == "12345678"


def test_end_to_end_exchange_me_and_records(tmp_path: Path):
    platform_dir = tmp_path / "platform"
    platform_dir.mkdir()
    db_path = platform_dir / "platform.sqlite3"
    env_path = platform_dir / ".env"
    env_path.write_text(
        f"PASSPORT_PLATFORM_DB_PATH={db_path.name}\n",
        encoding="utf-8",
    )

    services = build_services(
        type(
            "Settings",
            (),
            {
                "platform_env_file": env_path,
                "platform_root_dir": platform_dir,
            },
        )()
    )
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
            has_face=True,
            is_complete=True,
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            face_crop_uri="/tmp/face.jpg",
            core_result_json='{"data":{"PassportNumber":"12345678"}}',
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
