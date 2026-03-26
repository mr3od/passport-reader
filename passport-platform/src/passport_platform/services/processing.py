from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from uuid import uuid4

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

CONFIDENCE_AUTO_THRESHOLD = 0.85

if TYPE_CHECKING:
    from passport_core.extraction.models import ExtractionResult


class ExtractorProtocol(Protocol):
    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> ExtractionResult: ...


class ProcessingService:
    def __init__(
        self,
        *,
        users: UserService,
        quotas: QuotaService,
        uploads: UploadService,
        extractor: ExtractorProtocol,
        artifacts: ArtifactStore,
    ) -> None:
        self.users = users
        self.quotas = quotas
        self.uploads = uploads
        self.extractor = extractor
        self.artifacts = artifacts

    def close(self) -> None:
        """No-op to preserve adapter lifecycle compatibility."""

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
            extraction_result = self.extractor.extract(command.payload, mime_type=command.mime_type)
        except Exception as exc:
            try:
                processing_result = self.uploads.record_processing_result(
                    user.id,
                    RecordProcessingResultCommand(
                        upload_id=upload.id,
                        is_passport=False,
                        is_complete=False,
                        review_status="needs_review",
                        passport_image_uri=passport_image_uri,
                        confidence_overall=None,
                        extraction_result_json=json.dumps(
                            {
                                "trace_id": trace_id,
                                "error_details": artifact_errors
                                + [
                                    {
                                        "code": "INTERNAL_ERROR",
                                        "stage": "extract",
                                        "message": str(exc),
                                        "retryable": False,
                                    }
                                ],
                            },
                            ensure_ascii=True,
                            separators=(",", ":"),
                        ),
                        error_code="extractor_exception",
                    ),
                )
            except Exception:
                # Last resort: move upload out of PROCESSING so it never stays stuck.
                self.uploads.uploads.update_status(upload.id, UploadStatus.FAILED)
                raise
            final_upload = self._load_upload(upload.id)
            tracked = TrackedProcessingResult(
                user=user,
                upload=final_upload,
                quota_decision=quota_decision,
                extraction_result=None,
                processing_result=processing_result,
            )
            raise ProcessingFailedError(tracked, exc) from exc

        is_passport = bool(extraction_result.meta.is_passport) if extraction_result.meta else False
        passport_number = extraction_result.data.PassportNumber
        is_complete = is_passport and passport_number is not None
        review_status = _review_status(extraction_result) if is_passport else "needs_review"
        confidence_overall = (
            extraction_result.confidence.overall
            if extraction_result.confidence is not None
            else None
        )
        processing_result = self.uploads.record_processing_result(
            user.id,
            RecordProcessingResultCommand(
                upload_id=upload.id,
                is_passport=is_passport,
                is_complete=is_complete,
                review_status=review_status,
                passport_number=passport_number,
                passport_image_uri=passport_image_uri,
                confidence_overall=confidence_overall,
                extraction_result_json=extraction_result.model_dump_json(),
                error_code=_result_error_code(is_passport=is_passport, is_complete=is_complete),
            ),
        )
        final_upload = self._load_upload(upload.id)
        return TrackedProcessingResult(
            user=user,
            upload=final_upload,
            quota_decision=quota_decision,
            extraction_result=extraction_result,
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


def _review_status(extraction_result: ExtractionResult) -> str:
    confidence = extraction_result.confidence
    if confidence is None or confidence.overall is None:
        return "needs_review"
    if confidence.overall < CONFIDENCE_AUTO_THRESHOLD:
        return "needs_review"
    if extraction_result.warnings:
        return "needs_review"
    return "auto"


def _result_error_code(*, is_passport: bool, is_complete: bool) -> str | None:
    if is_complete:
        return None
    if not is_passport:
        return "not_passport"
    return "incomplete_extraction"


def _artifact_filename(upload_id: int, filename: str) -> str:
    return f"upload-{upload_id}{Path(filename).suffix or '.bin'}"
