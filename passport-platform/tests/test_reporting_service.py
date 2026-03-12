from __future__ import annotations

from datetime import UTC, datetime

from passport_platform.db import Database
from passport_platform.enums import ChannelName, ExternalProvider, UsageEventType, UserStatus
from passport_platform.repositories.reporting import ReportingRepository
from passport_platform.repositories.uploads import UploadsRepository
from passport_platform.repositories.usage import UsageRepository
from passport_platform.repositories.users import UsersRepository
from passport_platform.schemas.commands import (
    EnsureUserCommand,
    RecordProcessingResultCommand,
    RegisterUploadCommand,
)
from passport_platform.services.quotas import QuotaService
from passport_platform.services.reporting import ReportingService
from passport_platform.services.uploads import UploadService
from passport_platform.services.users import UserService


def test_get_user_usage_report_returns_month_counts_and_quota(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    usage = UsageRepository(db)
    quotas = QuotaService(usage)
    uploads = UploadService(UploadsRepository(db), usage)
    reporting = ReportingService(
        users=users,
        quotas=quotas,
        reporting=ReportingRepository(db),
    )
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
            completed_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
        ),
    )
    usage.record(
        user_id=user.id,
        event_type=UsageEventType.FAILED_PROCESS,
        created_at=datetime(2026, 3, 15, 13, 0, tzinfo=UTC),
    )

    report = reporting.get_user_usage_report(user.id, at=datetime(2026, 3, 20, tzinfo=UTC))

    assert report.user.id == user.id
    assert report.upload_count == 1
    assert report.success_count == 1
    assert report.failure_count == 1
    assert report.quota_decision.remaining_uploads == 19


def test_get_monthly_usage_report_aggregates_users_and_events(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    usage = UsageRepository(db)
    reporting = ReportingService(
        users=users,
        quotas=QuotaService(usage),
        reporting=ReportingRepository(db),
    )
    first = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
        )
    )
    second = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="67890",
        )
    )
    users.change_status(second.id, UserStatus.BLOCKED)
    now = datetime(2026, 3, 5, 10, 0, tzinfo=UTC)
    usage.record(user_id=first.id, event_type=UsageEventType.UPLOAD_RECEIVED, created_at=now)
    usage.record(user_id=first.id, event_type=UsageEventType.SUCCESSFUL_PROCESS, created_at=now)
    usage.record(user_id=second.id, event_type=UsageEventType.UPLOAD_RECEIVED, created_at=now)
    usage.record(user_id=second.id, event_type=UsageEventType.FAILED_PROCESS, created_at=now)

    report = reporting.get_monthly_usage_report(at=now)

    assert report.total_users == 2
    assert report.active_users == 1
    assert report.blocked_users == 1
    assert report.total_uploads == 2
    assert report.total_successes == 1
    assert report.total_failures == 1


def test_list_recent_uploads_returns_latest_first_with_joined_fields(tmp_path) -> None:
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users = UserService(UsersRepository(db))
    usage = UsageRepository(db)
    uploads = UploadService(UploadsRepository(db), usage)
    reporting = ReportingService(
        users=users,
        quotas=QuotaService(usage),
        reporting=ReportingRepository(db),
    )
    user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    first = uploads.register_upload(
        RegisterUploadCommand(
            user_id=user.id,
            channel=ChannelName.TELEGRAM,
            filename="first.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://chat/1/message/1/file/a",
        )
    )
    uploads.record_processing_result(
        user.id,
        RecordProcessingResultCommand(
            upload_id=first.id,
            is_passport=False,
            has_face=False,
            is_complete=False,
            error_code="not_passport",
            completed_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
        ),
    )
    second = uploads.register_upload(
        RegisterUploadCommand(
            user_id=user.id,
            channel=ChannelName.TELEGRAM,
            filename="second.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://chat/1/message/2/file/b",
        )
    )
    uploads.record_processing_result(
        user.id,
        RecordProcessingResultCommand(
            upload_id=second.id,
            is_passport=True,
            has_face=True,
            is_complete=True,
            passport_number="87654321",
            completed_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        ),
    )

    recent = reporting.list_recent_uploads(limit=2)

    assert len(recent) == 2
    assert recent[0].filename == "second.jpg"
    assert recent[0].passport_number == "87654321"
    assert recent[1].error_code == "not_passport"
