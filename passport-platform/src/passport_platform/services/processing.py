from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

import numpy as np

from passport_platform.enums import ChannelName, ExternalProvider, UploadStatus, UserStatus
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
from passport_platform.storage import ArtifactStore

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

    def load_bytes(
        self,
        data: bytes,
        *,
        filename: str = "upload.jpg",
        mime_type: str = "image/jpeg",
        source: str | None = None,
    ): ...

    def close(self) -> None: ...


class ProcessingService:
    def __init__(
        self,
        *,
        users: UserService,
        quotas: QuotaService,
        uploads: UploadService,
        workflow: WorkflowProtocol,
        artifacts: ArtifactStore,
    ) -> None:
        self.users = users
        self.quotas = quotas
        self.uploads = uploads
        self.workflow = workflow
        self.artifacts = artifacts

    def close(self) -> None:
        self.workflow.close()

    def process_bytes(self, command: ProcessUploadCommand) -> TrackedProcessingResult:
        trace_id = uuid4().hex
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

        upload, quota_decision = self.uploads.reserve_upload(
            user=user,
            quotas=self.quotas,
            command=RegisterUploadCommand(
                user_id=user.id,
                channel=channel,
                filename=command.filename,
                mime_type=command.mime_type,
                source_ref=command.source_ref,
                external_message_id=command.external_message_id,
                external_file_id=command.external_file_id,
            ),
        )
        upload = self.uploads.mark_processing(upload.id)
        artifact_errors: list[dict[str, Any]] = []
        passport_image_uri = self._store_original_upload(command, upload.id, artifact_errors)

        try:
            workflow_result = self.workflow.process_bytes(
                command.payload,
                filename=command.filename,
                mime_type=command.mime_type,
                source=command.source_ref,
            )
        except Exception as exc:
            workflow_result = self._failed_workflow_result(command)
            try:
                processing_result = self.uploads.record_processing_result(
                    user.id,
                    RecordProcessingResultCommand(
                        upload_id=upload.id,
                        is_passport=False,
                        has_face=False,
                        is_complete=False,
                        passport_image_uri=passport_image_uri,
                        core_result_json=_serialize_workflow_result(
                            workflow_result,
                            trace_id=trace_id,
                            passport_image_uri=passport_image_uri,
                            face_crop_uri=None,
                            error_details=artifact_errors
                            + [
                                {
                                    "code": "INTERNAL_ERROR",
                                    "stage": "workflow",
                                    "message": str(exc),
                                    "retryable": False,
                                }
                            ],
                        ),
                        error_code="workflow_exception",
                    ),
                )
            except Exception:
                # Last resort: at minimum move the upload out of PROCESSING
                # so it does not stay stuck forever.
                self.uploads.uploads.update_status(upload.id, UploadStatus.FAILED)
                raise
            final_upload = self._load_upload(upload.id)
            tracked = TrackedProcessingResult(
                user=user,
                upload=final_upload,
                quota_decision=quota_decision,
                workflow_result=workflow_result,
                processing_result=processing_result,
            )
            raise ProcessingFailedError(tracked, exc) from exc

        face_crop_uri = self._store_face_crop(workflow_result, upload.id, artifact_errors)
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
                passport_image_uri=passport_image_uri,
                face_crop_uri=face_crop_uri,
                core_result_json=_serialize_workflow_result(
                    workflow_result,
                    trace_id=trace_id,
                    passport_image_uri=passport_image_uri,
                    face_crop_uri=face_crop_uri,
                    error_details=artifact_errors + _workflow_error_details(workflow_result),
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

    def _store_original_upload(
        self,
        command: ProcessUploadCommand,
        upload_id: int,
        errors: list[dict[str, Any]],
    ) -> str | None:
        return self._store_artifact(
            data=command.payload,
            folder="uploads",
            filename=_artifact_filename(upload_id, command.filename),
            content_type=command.mime_type,
            stage="store_original",
            errors=errors,
        )

    def _store_face_crop(
        self,
        workflow_result: PassportWorkflowResult,
        upload_id: int,
        errors: list[dict[str, Any]],
    ) -> str | None:
        if workflow_result.face_crop_bytes is None:
            return None
        return self._store_artifact(
            data=workflow_result.face_crop_bytes,
            folder="faces",
            filename=f"upload-{upload_id}-face.jpg",
            content_type="image/jpeg",
            stage="store_face_crop",
            errors=errors,
        )

    def _store_artifact(
        self,
        *,
        data: bytes,
        folder: str,
        filename: str,
        content_type: str,
        stage: str,
        errors: list[dict[str, Any]],
    ) -> str | None:
        try:
            return self.artifacts.save(
                data,
                folder=folder,
                filename=filename,
                content_type=content_type,
            )
        except Exception as exc:
            errors.append(
                {
                    "code": "STORAGE_ERROR",
                    "stage": stage,
                    "message": str(exc),
                    "retryable": False,
                }
            )
            return None

    def _failed_workflow_result(self, command: ProcessUploadCommand):
        from passport_core.workflow import PassportWorkflowResult, ValidationResult

        try:
            loaded = self.workflow.load_bytes(
                command.payload,
                filename=command.filename,
                mime_type=command.mime_type,
                source=command.source_ref,
            )
        except Exception:
            from passport_core.workflow import LoadedImage

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


def _result_error_code(workflow_result: PassportWorkflowResult) -> str | None:
    if workflow_result.is_complete:
        return None
    if not workflow_result.validation.is_passport:
        return "not_passport"
    if not workflow_result.has_face_crop:
        return "face_crop_failed"
    return "incomplete_processing"


def _serialize_workflow_result(
    workflow_result: PassportWorkflowResult,
    *,
    trace_id: str,
    passport_image_uri: str | None,
    face_crop_uri: str | None,
    error_details: list[dict[str, Any]] | None = None,
) -> str:
    payload = {
        "source": workflow_result.source,
        "trace_id": trace_id,
        "passport_image_uri": passport_image_uri,
        "face_crop_uri": face_crop_uri,
        "validation": workflow_result.validation.model_dump(mode="json"),
        "face": (
            workflow_result.face.model_dump(mode="json")
            if workflow_result.face is not None
            else None
        ),
        "data": (
            workflow_result.data.model_dump(mode="json")
            if workflow_result.data is not None
            else None
        ),
        "error_details": error_details or [],
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _workflow_error_details(workflow_result: PassportWorkflowResult) -> list[dict[str, Any]]:
    if workflow_result.is_complete:
        return []
    if not workflow_result.validation.is_passport:
        return [
            {
                "code": "VALIDATION_ERROR",
                "stage": "validate",
                "message": "The uploaded image did not validate as a passport.",
                "retryable": False,
            }
        ]
    if not workflow_result.has_face_crop:
        return [
            {
                "code": "FACE_DETECTION_ERROR",
                "stage": "face_detect",
                "message": "No face crop could be produced from the passport image.",
                "retryable": False,
            }
        ]
    return [
        {
            "code": "EXTRACTION_ERROR",
            "stage": "extract",
            "message": "Passport extraction did not complete successfully.",
            "retryable": True,
        }
    ]


def _artifact_filename(upload_id: int, filename: str) -> str:
    return f"upload-{upload_id}{Path(filename).suffix or '.bin'}"
