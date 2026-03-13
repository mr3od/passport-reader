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


def test_initialize_upgrades_processing_results_table_for_core_payload(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    with db.transaction() as conn:
        conn.executescript(
            """
            CREATE TABLE processing_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upload_id INTEGER NOT NULL UNIQUE,
                is_passport INTEGER NOT NULL,
                has_face INTEGER NOT NULL,
                is_complete INTEGER NOT NULL,
                passport_number TEXT,
                error_code TEXT,
                completed_at TEXT NOT NULL
            );
            """
        )

    db.initialize()

    with db.connect() as conn:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(processing_results)").fetchall()
        }
    assert "passport_image_uri" in columns
    assert "face_crop_uri" in columns
    assert "core_result_json" in columns


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
    assert usage.sum_units_for_period(
        user_id=user.id,
        event_type=UsageEventType.UPLOAD_RECEIVED,
        period_start=period_start,
        period_end=period_end,
    ) == 1


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
            has_face=True,
            is_complete=True,
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            face_crop_uri="/tmp/face.jpg",
            core_result_json='{"trace_id":"demo","data":{"PassportNumber":"12345678"}}',
        ),
    )
    stored_upload = uploads.get_by_id(upload.id)

    assert result.is_complete is True
    assert result.passport_image_uri == "/tmp/original.jpg"
    assert result.face_crop_uri == "/tmp/face.jpg"
    assert result.core_result_json is not None
    assert json.loads(result.core_result_json)["trace_id"] == "demo"
    assert stored_upload is not None
    assert stored_upload.status is UploadStatus.PROCESSED
    period_start, period_end = _month_window(stored_upload.created_at)
    assert usage.sum_units_for_period(
        user_id=user.id,
        event_type=UsageEventType.SUCCESSFUL_PROCESS,
        period_start=period_start,
        period_end=period_end,
    ) == 1
