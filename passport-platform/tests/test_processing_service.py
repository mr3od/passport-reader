from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from passport_core.io import encode_jpeg, load_image_bytes
from passport_core.models import (
    BoundingBox,
    FaceCropResult,
    FaceDetectionResult,
    PassportData,
    ValidationResult,
)
from passport_core.workflow import PassportWorkflowResult

from passport_platform.db import Database
from passport_platform.enums import (
    ChannelName,
    ExternalProvider,
    PlanName,
    UsageEventType,
    UserStatus,
)
from passport_platform.errors import (
    ProcessingFailedError,
    QuotaExceededError,
    UnsupportedChannelError,
    UnsupportedExternalProviderError,
    UserBlockedError,
)
from passport_platform.repositories.uploads import UploadsRepository
from passport_platform.repositories.usage import UsageRepository
from passport_platform.repositories.users import UsersRepository
from passport_platform.schemas.commands import EnsureUserCommand, ProcessUploadCommand
from passport_platform.services.processing import ProcessingService
from passport_platform.services.quotas import QuotaService
from passport_platform.services.uploads import UploadService
from passport_platform.services.users import UserService


class FakeWorkflow:
    def __init__(
        self,
        result: PassportWorkflowResult | None = None,
        error: Exception | None = None,
    ):
        self.result = result
        self.error = error
        self.closed = False

    def process_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        mime_type: str,
        source: str | None = None,
    ):
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise RuntimeError("fake workflow result was not configured")
        return self.result

    def close(self) -> None:
        self.closed = True


class BlockingWorkflow(FakeWorkflow):
    def __init__(self, result: PassportWorkflowResult) -> None:
        super().__init__(result=result)
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def process_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        mime_type: str,
        source: str | None = None,
    ):
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            assert self.release.wait(timeout=5)
        return super().process_bytes(
            data,
            filename=filename,
            mime_type=mime_type,
            source=source,
        )


class CoordinatedUsageRepository(UsageRepository):
    def __init__(self, db: Database) -> None:
        super().__init__(db)
        self._barrier = threading.Barrier(2)
        self._lock = threading.Lock()
        self._remaining_sync_calls = 2

    def sum_units_for_period(
        self,
        *,
        user_id: int,
        event_type: UsageEventType,
        period_start,
        period_end,
        conn=None,
    ) -> int:
        should_sync = False
        with self._lock:
            if (
                conn is None
                and event_type is UsageEventType.UPLOAD_RECEIVED
                and self._remaining_sync_calls > 0
            ):
                self._remaining_sync_calls -= 1
                should_sync = True
        if should_sync:
            self._barrier.wait(timeout=5)
        return super().sum_units_for_period(
            user_id=user_id,
            event_type=event_type,
            period_start=period_start,
            period_end=period_end,
            conn=conn,
        )


def test_processing_service_creates_user_and_persists_successful_result(tmp_path) -> None:
    service, usage = build_processing_service(
        tmp_path,
        workflow=FakeWorkflow(result=make_workflow_result(complete=True)),
    )

    tracked = service.process_bytes(
        ProcessUploadCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            channel=ChannelName.TELEGRAM,
            filename="passport.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://chat/1/message/2/file/abc",
            payload=JPEG_BYTES,
            display_name="Agency A",
        )
    )

    assert tracked.user.display_name == "Agency A"
    assert tracked.processing_result.is_complete is True
    assert tracked.processing_result.passport_number == "12345678"
    assert tracked.upload.status.value == "processed"
    assert usage_total(usage, tracked.user.id, UsageEventType.UPLOAD_RECEIVED) == 1
    assert usage_total(usage, tracked.user.id, UsageEventType.SUCCESSFUL_PROCESS) == 1


def test_processing_service_rejects_blocked_user(tmp_path) -> None:
    service, _ = build_processing_service(
        tmp_path,
        workflow=FakeWorkflow(result=make_workflow_result(complete=True)),
    )
    blocked_user = service.users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    service.users.change_status(blocked_user.id, UserStatus.BLOCKED)

    with pytest.raises(UserBlockedError):
        service.process_bytes(
            ProcessUploadCommand(
                external_provider=ExternalProvider.TELEGRAM,
                external_user_id="12345",
                channel=ChannelName.TELEGRAM,
                filename="passport.jpg",
                mime_type="image/jpeg",
                source_ref="telegram://chat/1/message/2/file/abc",
                payload=JPEG_BYTES,
            )
        )


def test_processing_service_rejects_quota_before_registering_upload(tmp_path) -> None:
    service, usage = build_processing_service(
        tmp_path,
        workflow=FakeWorkflow(result=make_workflow_result(complete=True)),
    )
    user = service.users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            default_plan=PlanName.FREE,
        )
    )
    for _ in range(20):
        usage.record(user_id=user.id, event_type=UsageEventType.UPLOAD_RECEIVED)

    with pytest.raises(QuotaExceededError):
        service.process_bytes(
            ProcessUploadCommand(
                external_provider=ExternalProvider.TELEGRAM,
                external_user_id="12345",
                channel=ChannelName.TELEGRAM,
                filename="passport.jpg",
                mime_type="image/jpeg",
                source_ref="telegram://chat/1/message/2/file/abc",
                payload=JPEG_BYTES,
            )
        )

    assert service.uploads.uploads.get_by_source_ref("telegram://chat/1/message/2/file/abc") is None


def test_processing_service_records_failed_result_when_workflow_raises(tmp_path) -> None:
    service, usage = build_processing_service(
        tmp_path,
        workflow=FakeWorkflow(error=RuntimeError("boom")),
    )

    with pytest.raises(ProcessingFailedError) as exc_info:
        service.process_bytes(
            ProcessUploadCommand(
                external_provider=ExternalProvider.TELEGRAM,
                external_user_id="12345",
                channel=ChannelName.TELEGRAM,
                filename="passport.jpg",
                mime_type="image/jpeg",
                source_ref="telegram://chat/1/message/2/file/abc",
                payload=JPEG_BYTES,
            )
        )

    tracked = exc_info.value.result
    assert tracked.processing_result.is_complete is False
    assert tracked.processing_result.error_code == "workflow_exception"
    assert tracked.upload.status.value == "failed"
    assert usage_total(usage, tracked.user.id, UsageEventType.UPLOAD_RECEIVED) == 1
    assert usage_total(usage, tracked.user.id, UsageEventType.FAILED_PROCESS) == 1


def test_processing_service_reserves_upload_slot_atomically(tmp_path) -> None:
    workflow = BlockingWorkflow(result=make_workflow_result(complete=True))
    service, usage = build_processing_service(
        tmp_path,
        workflow=workflow,
        usage_repository_cls=CoordinatedUsageRepository,
    )
    user = service.users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            default_plan=PlanName.FREE,
        )
    )
    for _ in range(19):
        usage.record(user_id=user.id, event_type=UsageEventType.UPLOAD_RECEIVED)

    command_one = ProcessUploadCommand(
        external_provider=ExternalProvider.TELEGRAM,
        external_user_id="12345",
        channel=ChannelName.TELEGRAM,
        filename="passport-1.jpg",
        mime_type="image/jpeg",
        source_ref="telegram://chat/1/message/2/file/one",
        payload=JPEG_BYTES,
    )
    command_two = ProcessUploadCommand(
        external_provider=ExternalProvider.TELEGRAM,
        external_user_id="12345",
        channel=ChannelName.TELEGRAM,
        filename="passport-2.jpg",
        mime_type="image/jpeg",
        source_ref="telegram://chat/1/message/2/file/two",
        payload=JPEG_BYTES,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_one = executor.submit(service.process_bytes, command_one)
        assert workflow.started.wait(timeout=5)
        future_two = executor.submit(service.process_bytes, command_two)
        workflow.release.set()

        tracked = future_one.result(timeout=5)
        with pytest.raises(QuotaExceededError):
            future_two.result(timeout=5)

    usage._remaining_sync_calls = 0
    assert tracked.processing_result.is_complete is True
    assert usage_total(usage, user.id, UsageEventType.UPLOAD_RECEIVED) == 20
    assert usage_total(usage, user.id, UsageEventType.SUCCESSFUL_PROCESS) == 1


def test_processing_service_rejects_unsupported_provider_and_channel(tmp_path) -> None:
    service, _ = build_processing_service(
        tmp_path,
        workflow=FakeWorkflow(result=make_workflow_result(complete=True)),
    )

    with pytest.raises(UnsupportedExternalProviderError):
        service.process_bytes(
            ProcessUploadCommand(
                external_provider="whatsapp",
                external_user_id="12345",
                channel=ChannelName.TELEGRAM,
                filename="passport.jpg",
                mime_type="image/jpeg",
                source_ref="telegram://chat/1/message/2/file/abc",
                payload=JPEG_BYTES,
            )
        )

    with pytest.raises(UnsupportedChannelError):
        service.process_bytes(
            ProcessUploadCommand(
                external_provider=ExternalProvider.TELEGRAM,
                external_user_id="12345",
                channel="whatsapp",
                filename="passport.jpg",
                mime_type="image/jpeg",
                source_ref="telegram://chat/1/message/2/file/abc",
                payload=JPEG_BYTES,
            )
        )


def build_processing_service(
    tmp_path,
    *,
    workflow: FakeWorkflow,
    usage_repository_cls: type[UsageRepository] = UsageRepository,
):
    db = Database(tmp_path / "platform.sqlite3")
    db.initialize()
    users_repo = UsersRepository(db)
    uploads_repo = UploadsRepository(db)
    usage_repo = usage_repository_cls(db)
    service = ProcessingService(
        users=UserService(users_repo),
        quotas=QuotaService(usage_repo),
        uploads=UploadService(uploads_repo, usage_repo),
        workflow=workflow,
    )
    return service, usage_repo


def make_workflow_result(*, complete: bool) -> PassportWorkflowResult:
    loaded = load_image_bytes(
        JPEG_BYTES,
        filename="passport.jpg",
        mime_type="image/jpeg",
        source="telegram://chat/1/message/2/file/abc",
    )
    if complete:
        return PassportWorkflowResult(
            loaded=loaded,
            validation=ValidationResult(
                is_passport=True,
                page_quad=[(0, 0), (10, 0), (10, 10), (0, 10)],
            ),
            face=FaceDetectionResult(
                bbox_original=BoundingBox(x=1, y=1, width=2, height=2),
            ),
            face_crop=FaceCropResult(
                bbox_original=BoundingBox(x=1, y=1, width=2, height=2),
                width=2,
                height=2,
                jpeg_bytes=b"face",
            ),
            data=PassportData(PassportNumber="12345678"),
        )
    return PassportWorkflowResult(
        loaded=loaded,
        validation=ValidationResult(is_passport=False),
    )


def usage_total(usage: UsageRepository, user_id: int, event_type: UsageEventType) -> int:
    from datetime import UTC, datetime

    return usage.sum_units_for_period(
        user_id=user_id,
        event_type=event_type,
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2027, 1, 1, tzinfo=UTC),
    )


JPEG_BYTES = encode_jpeg(np.full((8, 8, 3), 255, dtype=np.uint8))
