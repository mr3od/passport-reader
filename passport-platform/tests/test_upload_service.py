from __future__ import annotations

import json

from passport_platform.db import Database
from passport_platform.enums import ChannelName, ExternalProvider, UploadStatus, UsageEventType
from passport_platform.repositories.uploads import UploadsRepository
from passport_platform.repositories.usage import UsageRepository
from passport_platform.repositories.users import UsersRepository
from passport_platform.schemas.commands import (
    EnsureUserCommand,
    RecordProcessingResultCommand,
    RegisterUploadCommand,
)
from passport_platform.services.uploads import UploadService
from passport_platform.services.users import UserService


def _month_window(timestamp):
    start = timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if timestamp.month == 12:
        end = start.replace(year=timestamp.year + 1, month=1)
    else:
        end = start.replace(month=timestamp.month + 1)
    return start, end


def test_initialize_creates_v2_processing_results_and_masar_tables(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()

    with db.connect() as conn:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(processing_results)").fetchall()
        }
        masar_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(masar_submissions)").fetchall()
        }
        masar_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='masar_submissions'"
        ).fetchone()
    assert "passport_image_uri" in columns
    assert "confidence_overall" in columns
    assert "review_status" in columns
    assert "extraction_result_json" in columns
    assert masar_table is not None
    assert "masar_detail_id" in masar_columns


def test_register_upload_creates_upload_and_usage_entry(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UsersRepository(db)
    user = UserService(users).get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
        )
    )
    uploads = UploadsRepository(db)
    usage = UsageRepository(db)
    service = UploadService(uploads, usage)

    upload = service.register_upload(
        RegisterUploadCommand(
            user_id=user.id,
            channel=ChannelName.TELEGRAM,
            filename="passport.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://chat/1/message/2/file/abc",
            external_message_id="2",
            external_file_id="abc",
        )
    )

    assert upload.status is UploadStatus.RECEIVED
    period_start, period_end = _month_window(upload.created_at)
    assert (
        usage.sum_units_for_period(
            user_id=user.id,
            event_type=UsageEventType.UPLOAD_RECEIVED,
            period_start=period_start,
            period_end=period_end,
        )
        == 1
    )


def test_record_processing_result_marks_upload_complete_and_records_usage(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    user = UserService(UsersRepository(db)).get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
        )
    )
    uploads = UploadsRepository(db)
    usage = UsageRepository(db)
    service = UploadService(uploads, usage)
    upload = service.register_upload(
        RegisterUploadCommand(
            user_id=user.id,
            channel=ChannelName.TELEGRAM,
            filename="passport.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://chat/1/message/2/file/abc",
        )
    )

    service.mark_processing(upload.id)
    result = service.record_processing_result(
        user.id,
        RecordProcessingResultCommand(
            upload_id=upload.id,
            is_passport=True,
            is_complete=True,
            review_status="auto",
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            confidence_overall=0.98,
            extraction_result_json='{"data":{"PassportNumber":"12345678"}}',
        ),
    )
    stored_upload = uploads.get_by_id(upload.id)

    assert result.is_complete is True
    assert result.passport_image_uri == "/tmp/original.jpg"
    assert result.confidence_overall == 0.98
    assert result.extraction_result_json is not None
    assert json.loads(result.extraction_result_json)["data"]["PassportNumber"] == "12345678"
    assert stored_upload is not None
    assert stored_upload.status is UploadStatus.PROCESSED
    period_start, period_end = _month_window(stored_upload.created_at)
    assert (
        usage.sum_units_for_period(
            user_id=user.id,
            event_type=UsageEventType.SUCCESSFUL_PROCESS,
            period_start=period_start,
            period_end=period_end,
        )
        == 1
    )
