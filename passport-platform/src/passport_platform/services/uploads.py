from __future__ import annotations

from passport_platform.enums import UploadStatus, UsageEventType
from passport_platform.models.upload import ProcessingResult, Upload
from passport_platform.repositories.uploads import UploadsRepository
from passport_platform.repositories.usage import UsageRepository
from passport_platform.schemas.commands import RecordProcessingResultCommand, RegisterUploadCommand


class UploadService:
    def __init__(
        self,
        uploads: UploadsRepository,
        usage: UsageRepository,
    ) -> None:
        self.uploads = uploads
        self.usage = usage

    def register_upload(self, command: RegisterUploadCommand) -> Upload:
        upload = self.uploads.create(command)
        self.usage.record(
            user_id=command.user_id,
            upload_id=upload.id,
            event_type=UsageEventType.UPLOAD_RECEIVED,
            units=1,
        )
        return upload

    def get_upload(self, upload_id: int) -> Upload | None:
        return self.uploads.get_by_id(upload_id)

    def mark_processing(self, upload_id: int) -> Upload:
        return self.uploads.update_status(upload_id, UploadStatus.PROCESSING)

    def record_processing_result(
        self,
        user_id: int,
        command: RecordProcessingResultCommand,
    ) -> ProcessingResult:
        result = self.uploads.create_processing_result(command)
        status = UploadStatus.PROCESSED if command.is_complete else UploadStatus.FAILED
        self.uploads.update_status(command.upload_id, status)
        self.usage.record(
            user_id=user_id,
            upload_id=command.upload_id,
            event_type=(
                UsageEventType.SUCCESSFUL_PROCESS
                if command.is_complete
                else UsageEventType.FAILED_PROCESS
            ),
            units=1,
        )
        return result
