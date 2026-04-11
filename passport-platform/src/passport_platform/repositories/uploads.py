from __future__ import annotations

import sqlite3
from contextlib import nullcontext
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
                    created_at,
                    archived_at
                FROM uploads
                WHERE id = ?
                """,
                (upload_id,),
            ).fetchone()
        return _row_to_upload(row)

    def get_by_source_ref(self, source_ref: str) -> Upload | None:
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
                    created_at,
                    archived_at
                FROM uploads
                WHERE source_ref = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (source_ref,),
            ).fetchone()
        return _row_to_upload(row)

    def create(
        self,
        command: RegisterUploadCommand,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> Upload:
        created_at = datetime.now(UTC)
        context = nullcontext(conn) if conn is not None else self.db.transaction()
        with context as active_conn:
            cursor = active_conn.execute(
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
            assert cursor.lastrowid is not None
            upload_id = cursor.lastrowid
        if conn is not None:
            return Upload(
                id=upload_id,
                user_id=command.user_id,
                channel=command.channel,
                external_message_id=command.external_message_id,
                external_file_id=command.external_file_id,
                filename=command.filename,
                mime_type=command.mime_type,
                source_ref=command.source_ref,
                status=UploadStatus.RECEIVED,
                created_at=created_at,
                archived_at=None,
            )
        upload = self.get_by_id(upload_id)
        if upload is None:
            raise RuntimeError("created upload could not be loaded")
        return upload

    def update_status(
        self,
        upload_id: int,
        status: UploadStatus,
        conn: sqlite3.Connection | None = None,
    ) -> Upload:
        context = nullcontext(conn) if conn is not None else self.db.transaction()
        with context as active_conn:
            active_conn.execute(
                "UPDATE uploads SET status = ? WHERE id = ?",
                (status.value, upload_id),
            )
        upload = self.get_by_id(upload_id)
        if upload is None:
            raise KeyError(f"upload {upload_id} not found")
        return upload

    def create_processing_result(
        self,
        command: RecordProcessingResultCommand,
        conn: sqlite3.Connection | None = None,
    ) -> ProcessingResult:
        completed_at = command.completed_at or datetime.now(UTC)
        context = nullcontext(conn) if conn is not None else self.db.transaction()
        with context as active_conn:
            cursor = active_conn.execute(
                """
                INSERT INTO processing_results (
                    upload_id,
                    is_passport,
                    is_complete,
                    review_status,
                    passport_number,
                    passport_image_uri,
                    confidence_overall,
                    extraction_result_json,
                    error_code,
                    completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.upload_id,
                    int(command.is_passport),
                    int(command.is_complete),
                    command.review_status,
                    command.passport_number,
                    command.passport_image_uri,
                    command.confidence_overall,
                    command.extraction_result_json,
                    command.error_code,
                    completed_at.isoformat(),
                ),
            )
            assert cursor.lastrowid is not None
            row_id = cursor.lastrowid
        # Build the result from known values — avoids a read-after-write that
        # would fail when called inside a shared (uncommitted) transaction.
        return ProcessingResult(
            id=row_id,
            upload_id=command.upload_id,
            is_passport=command.is_passport,
            is_complete=command.is_complete,
            review_status=command.review_status,
            reviewed_by_user_id=None,
            reviewed_at=None,
            passport_number=command.passport_number,
            passport_image_uri=command.passport_image_uri,
            confidence_overall=command.confidence_overall,
            extraction_result_json=command.extraction_result_json,
            error_code=command.error_code,
            completed_at=completed_at,
        )

    def get_processing_result(self, upload_id: int) -> ProcessingResult | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    upload_id,
                    is_passport,
                    is_complete,
                    review_status,
                    reviewed_by_user_id,
                    reviewed_at,
                    passport_number,
                    passport_image_uri,
                    confidence_overall,
                    extraction_result_json,
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
        archived_at=(
            datetime.fromisoformat(row["archived_at"]) if row["archived_at"] is not None else None
        ),
    )


def _row_to_processing_result(row) -> ProcessingResult | None:
    if row is None:
        return None
    return ProcessingResult(
        id=int(row["id"]),
        upload_id=int(row["upload_id"]),
        is_passport=bool(row["is_passport"]),
        is_complete=bool(row["is_complete"]),
        review_status=row["review_status"],
        reviewed_by_user_id=row["reviewed_by_user_id"],
        reviewed_at=(
            datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] is not None else None
        ),
        passport_number=row["passport_number"],
        passport_image_uri=row["passport_image_uri"],
        confidence_overall=row["confidence_overall"],
        extraction_result_json=row["extraction_result_json"],
        error_code=row["error_code"],
        completed_at=datetime.fromisoformat(row["completed_at"]),
    )
