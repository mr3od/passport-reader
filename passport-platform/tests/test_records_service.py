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
            is_complete=True,
            review_status="auto",
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            confidence_overall=0.97,
            extraction_result_json='{"source":"telegram://owned","data":{"PassportNumber":"12345678"}}',
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
            is_complete=False,
            review_status="needs_review",
            error_code="not_passport",
            completed_at=datetime(2026, 3, 13, 12, 5, tzinfo=UTC),
        ),
    )

    user_records = records.list_user_records(first_user.id)

    assert len(user_records) == 1
    assert user_records[0].filename == "owned.jpg"
    assert user_records[0].passport_number == "12345678"
    assert user_records[0].passport_image_uri == "/tmp/original.jpg"
    assert user_records[0].confidence_overall == 0.97
    assert user_records[0].review_status == "auto"
    assert user_records[0].extraction_result is not None
    assert user_records[0].extraction_result["data"]["PassportNumber"] == "12345678"


def test_update_masar_status_stores_detail_id_and_scan_result(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    uploads = UploadService(UploadsRepository(db), UsageRepository(db))
    records = RecordsService(RecordsRepository(db))
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
            source_ref="telegram://passport",
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
            confidence_overall=0.97,
            extraction_result_json='{"data":{"PassportNumber":"12345678"}}',
            completed_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        ),
    )

    updated = records.update_masar_status(
        upload_id=upload.id,
        user_id=user.id,
        status="submitted",
        masar_mutamer_id="M-1",
        masar_scan_result={"ok": True},
        masar_detail_id="detail-123",
    )
    record = records.get_user_record(user.id, upload.id)

    assert updated is True
    assert record is not None
    assert record.masar_status == "submitted"
    assert record.masar_mutamer_id == "M-1"
    assert record.masar_scan_result == {"ok": True}
    assert record.masar_detail_id == "detail-123"


def test_assert_submission_allowed_accepts_needs_review_records(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    uploads = UploadService(UploadsRepository(db), UsageRepository(db))
    records = RecordsService(RecordsRepository(db))
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
            source_ref="telegram://passport",
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
            completed_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        ),
    )

    records.assert_submission_allowed(upload_id=upload.id, user_id=user.id)
