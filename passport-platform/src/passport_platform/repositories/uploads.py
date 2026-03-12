from __future__ import annotations

from datetime import UTC, datetime

from passport_platform.db import Database
from passport_platform.enums import UploadStatus
from passport_platform.models.upload import ProcessingResult, Upload
from passport_platform.schemas.commands import RecordProcessingResultCommand, RegisterUploadCommand


class UploadsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get_by_id(self, upload_id: int) -> Upload | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    user_id,
                    channel,
                    external_message_id,
                    external_file_id,
                    filename,
                    mime_type,
                    source_ref,
                    status,
                    created_at
                FROM uploads
                WHERE id = ?
                """,
                (upload_id,),
            ).fetchone()
        return _row_to_upload(row)

    def create(self, command: RegisterUploadCommand) -> Upload:
        created_at = datetime.now(UTC)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO uploads (
                    user_id,
                    channel,
                    external_message_id,
                    external_file_id,
                    filename,
                    mime_type,
                    source_ref,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.user_id,
                    command.channel.value,
                    command.external_message_id,
                    command.external_file_id,
                    command.filename,
                    command.mime_type,
                    command.source_ref,
                    UploadStatus.RECEIVED.value,
                    created_at.isoformat(),
                ),
            )
            upload_id = int(cursor.lastrowid)
        upload = self.get_by_id(upload_id)
        if upload is None:
            raise RuntimeError("created upload could not be loaded")
        return upload

    def update_status(self, upload_id: int, status: UploadStatus) -> Upload:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE uploads SET status = ? WHERE id = ?",
                (status.value, upload_id),
            )
        upload = self.get_by_id(upload_id)
        if upload is None:
            raise KeyError(f"upload {upload_id} not found")
        return upload

    def create_processing_result(self, command: RecordProcessingResultCommand) -> ProcessingResult:
        completed_at = command.completed_at or datetime.now(UTC)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO processing_results (
                    upload_id,
                    is_passport,
                    has_face,
                    is_complete,
                    passport_number,
                    error_code,
                    completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.upload_id,
                    int(command.is_passport),
                    int(command.has_face),
                    int(command.is_complete),
                    command.passport_number,
                    command.error_code,
                    completed_at.isoformat(),
                ),
            )
            result_id = int(cursor.lastrowid)
        result = self.get_processing_result(command.upload_id)
        if result is None:
            raise RuntimeError(f"created processing result {result_id} could not be loaded")
        return result

    def get_processing_result(self, upload_id: int) -> ProcessingResult | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    upload_id,
                    is_passport,
                    has_face,
                    is_complete,
                    passport_number,
                    error_code,
                    completed_at
                FROM processing_results
                WHERE upload_id = ?
                """,
                (upload_id,),
            ).fetchone()
        return _row_to_processing_result(row)


def _row_to_upload(row) -> Upload | None:
    if row is None:
        return None
    from passport_platform.enums import ChannelName

    return Upload(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        channel=ChannelName(row["channel"]),
        external_message_id=row["external_message_id"],
        external_file_id=row["external_file_id"],
        filename=row["filename"],
        mime_type=row["mime_type"],
        source_ref=row["source_ref"],
        status=UploadStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_processing_result(row) -> ProcessingResult | None:
    if row is None:
        return None
    return ProcessingResult(
        id=int(row["id"]),
        upload_id=int(row["upload_id"]),
        is_passport=bool(row["is_passport"]),
        has_face=bool(row["has_face"]),
        is_complete=bool(row["is_complete"]),
        passport_number=row["passport_number"],
        error_code=row["error_code"],
        completed_at=datetime.fromisoformat(row["completed_at"]),
    )
