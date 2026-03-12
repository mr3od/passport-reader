from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import numpy as np

from passport_platform.enums import ChannelName, ExternalProvider, UserStatus
from passport_platform.errors import (
    ProcessingFailedError,
    UnsupportedChannelError,
    UnsupportedExternalProviderError,
    UserBlockedError,
)
from passport_platform.schemas.commands import (
    EnsureUserCommand,
    ProcessUploadCommand,
    RecordProcessingResultCommand,
    RegisterUploadCommand,
)
from passport_platform.schemas.results import TrackedProcessingResult
from passport_platform.services.quotas import QuotaService
from passport_platform.services.uploads import UploadService
from passport_platform.services.users import UserService

if TYPE_CHECKING:
    from passport_core.workflow import PassportWorkflowResult


class WorkflowProtocol(Protocol):
    def process_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        mime_type: str,
        source: str | None = None,
    ) -> PassportWorkflowResult: ...

    def close(self) -> None: ...


class ProcessingService:
    def __init__(
        self,
        *,
        users: UserService,
        quotas: QuotaService,
        uploads: UploadService,
        workflow: WorkflowProtocol,
    ) -> None:
        self.users = users
        self.quotas = quotas
        self.uploads = uploads
        self.workflow = workflow

    def close(self) -> None:
        self.workflow.close()

    def process_bytes(self, command: ProcessUploadCommand) -> TrackedProcessingResult:
        provider = self._provider(command.external_provider)
        channel = self._channel(command.channel)
        user = self.users.get_or_create_user(
            EnsureUserCommand(
                external_provider=provider,
                external_user_id=command.external_user_id,
                display_name=command.display_name,
                default_plan=command.default_plan,
            )
        )
        if user.status is UserStatus.BLOCKED:
            raise UserBlockedError(user)

        quota_decision = self.quotas.assert_can_upload(user)

        upload = self.uploads.register_upload(
            RegisterUploadCommand(
                user_id=user.id,
                channel=channel,
                filename=command.filename,
                mime_type=command.mime_type,
                source_ref=command.source_ref,
                external_message_id=command.external_message_id,
                external_file_id=command.external_file_id,
            )
        )
        upload = self.uploads.mark_processing(upload.id)

        try:
            workflow_result = self.workflow.process_bytes(
                command.payload,
                filename=command.filename,
                mime_type=command.mime_type,
                source=command.source_ref,
            )
        except Exception as exc:
            processing_result = self.uploads.record_processing_result(
                user.id,
                RecordProcessingResultCommand(
                    upload_id=upload.id,
                    is_passport=False,
                    has_face=False,
                    is_complete=False,
                    error_code="workflow_exception",
                ),
            )
            final_upload = self._load_upload(upload.id)
            tracked = TrackedProcessingResult(
                user=user,
                upload=final_upload,
                quota_decision=quota_decision,
                workflow_result=_failed_workflow_result(command),
                processing_result=processing_result,
            )
            raise ProcessingFailedError(tracked, exc) from exc

        processing_result = self.uploads.record_processing_result(
            user.id,
            RecordProcessingResultCommand(
                upload_id=upload.id,
                is_passport=workflow_result.validation.is_passport,
                has_face=workflow_result.has_face_crop,
                is_complete=workflow_result.is_complete,
                passport_number=(
                    workflow_result.data.PassportNumber
                    if workflow_result.data is not None
                    else None
                ),
                error_code=_result_error_code(workflow_result),
            ),
        )
        final_upload = self._load_upload(upload.id)
        return TrackedProcessingResult(
            user=user,
            upload=final_upload,
            quota_decision=quota_decision,
            workflow_result=workflow_result,
            processing_result=processing_result,
        )

    def _load_upload(self, upload_id: int):
        upload = self.uploads.get_upload(upload_id)
        if upload is None:
            raise RuntimeError(f"upload {upload_id} not found after processing")
        return upload

    @staticmethod
    def _provider(value: ExternalProvider | str) -> ExternalProvider:
        if isinstance(value, ExternalProvider):
            return value
        try:
            return ExternalProvider(value)
        except ValueError as exc:
            raise UnsupportedExternalProviderError(value) from exc

    @staticmethod
    def _channel(value: ChannelName | str) -> ChannelName:
        if isinstance(value, ChannelName):
            return value
        try:
            return ChannelName(value)
        except ValueError as exc:
            raise UnsupportedChannelError(value) from exc


def _result_error_code(workflow_result: PassportWorkflowResult) -> str | None:
    if workflow_result.is_complete:
        return None
    if not workflow_result.validation.is_passport:
        return "not_passport"
    if not workflow_result.has_face_crop:
        return "face_crop_failed"
    return "incomplete_processing"


def _failed_workflow_result(command: ProcessUploadCommand):
    from passport_core.io import LoadedImage, load_image_bytes
    from passport_core.models import ValidationResult
    from passport_core.workflow import PassportWorkflowResult

    try:
        loaded = load_image_bytes(
            command.payload,
            filename=command.filename,
            mime_type=command.mime_type,
            source=command.source_ref,
        )
    except Exception:
        loaded = LoadedImage(
            source=command.source_ref,
            data=command.payload,
            mime_type=command.mime_type,
            filename=command.filename,
            bgr=np.zeros((1, 1, 3), dtype=np.uint8),
        )
    return PassportWorkflowResult(
        loaded=loaded,
        validation=ValidationResult(is_passport=False),
    )
