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
                    created_at
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
                    created_at
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
            upload_id = int(cursor.lastrowid)
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
                    has_face,
                    is_complete,
                    passport_number,
                    passport_image_uri,
                    face_crop_uri,
                    core_result_json,
                    error_code,
                    completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.upload_id,
                    int(command.is_passport),
                    int(command.has_face),
                    int(command.is_complete),
                    command.passport_number,
                    command.passport_image_uri,
                    command.face_crop_uri,
                    command.core_result_json,
                    command.error_code,
                    completed_at.isoformat(),
                ),
            )
            row_id = int(cursor.lastrowid)
        # Build the result from known values — avoids a read-after-write that
        # would fail when called inside a shared (uncommitted) transaction.
        return ProcessingResult(
            id=row_id,
            upload_id=command.upload_id,
            is_passport=command.is_passport,
            has_face=command.has_face,
            is_complete=command.is_complete,
            passport_number=command.passport_number,
            passport_image_uri=command.passport_image_uri,
            face_crop_uri=command.face_crop_uri,
            core_result_json=command.core_result_json,
            error_code=command.error_code,
            completed_at=completed_at,
            masar_status=None,
            masar_mutamer_id=None,
            masar_scan_result_json=None,
        )

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
                    passport_image_uri,
                    face_crop_uri,
                    core_result_json,
                    error_code,
                    completed_at,
                    masar_status,
                    masar_mutamer_id,
                    masar_scan_result_json
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
        passport_image_uri=row["passport_image_uri"],
        face_crop_uri=row["face_crop_uri"],
        core_result_json=row["core_result_json"],
        error_code=row["error_code"],
        completed_at=datetime.fromisoformat(row["completed_at"]),
        masar_status=row["masar_status"],
        masar_mutamer_id=row["masar_mutamer_id"],
        masar_scan_result_json=row["masar_scan_result_json"],
    )
