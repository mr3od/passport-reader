from __future__ import annotations

from datetime import UTC, datetime

from passport_platform.db import Database
from passport_platform.enums import ChannelName, ExternalProvider
from passport_platform.repositories.records import RecordsRepository
from passport_platform.repositories.uploads import UploadsRepository
from passport_platform.repositories.usage import UsageRepository
from passport_platform.repositories.users import UsersRepository
from passport_platform.schemas.commands import (
    EnsureUserCommand,
    RecordProcessingResultCommand,
    RegisterUploadCommand,
)
from passport_platform.services.records import RecordsService
from passport_platform.services.uploads import UploadService
from passport_platform.services.users import UserService


def test_list_user_records_returns_only_owned_uploads(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    uploads = UploadService(UploadsRepository(db), UsageRepository(db))
    records = RecordsService(RecordsRepository(db))
    first_user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    second_user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="67890",
            display_name="Agency B",
        )
    )
    owned = uploads.register_upload(
        RegisterUploadCommand(
            user_id=first_user.id,
            channel=ChannelName.TELEGRAM,
            filename="owned.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://owned",
        )
    )
    uploads.record_processing_result(
        first_user.id,
        RecordProcessingResultCommand(
            upload_id=owned.id,
            is_passport=True,
            has_face=True,
            is_complete=True,
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            face_crop_uri="/tmp/face.jpg",
            core_result_json='{"source":"telegram://owned","data":{"PassportNumber":"12345678"}}',
            completed_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        ),
    )
    other = uploads.register_upload(
        RegisterUploadCommand(
            user_id=second_user.id,
            channel=ChannelName.TELEGRAM,
            filename="other.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://other",
        )
    )
    uploads.record_processing_result(
        second_user.id,
        RecordProcessingResultCommand(
            upload_id=other.id,
            is_passport=False,
            has_face=False,
            is_complete=False,
            error_code="not_passport",
            completed_at=datetime(2026, 3, 13, 12, 5, tzinfo=UTC),
        ),
    )

    user_records = records.list_user_records(first_user.id)

    assert len(user_records) == 1
    assert user_records[0].filename == "owned.jpg"
    assert user_records[0].passport_number == "12345678"
    assert user_records[0].passport_image_uri == "/tmp/original.jpg"
    assert user_records[0].face_crop_uri == "/tmp/face.jpg"
    assert user_records[0].core_result is not None
    assert user_records[0].core_result["data"]["PassportNumber"] == "12345678"
