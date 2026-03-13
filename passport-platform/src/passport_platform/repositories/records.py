from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from passport_platform.db import Database
from passport_platform.enums import UploadStatus
from passport_platform.schemas.results import UserRecord


class RecordsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list_user_records(self, user_id: int, *, limit: int = 50) -> list[UserRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    uploads.id AS upload_id,
                    uploads.user_id AS user_id,
                    uploads.filename AS filename,
                    uploads.mime_type AS mime_type,
                    uploads.source_ref AS source_ref,
                    uploads.status AS upload_status,
                    uploads.created_at AS created_at,
                    processing_results.completed_at AS completed_at,
                    processing_results.is_passport AS is_passport,
                    processing_results.has_face AS has_face,
                    processing_results.is_complete AS is_complete,
                    processing_results.passport_number AS passport_number,
                    processing_results.passport_image_uri AS passport_image_uri,
                    processing_results.face_crop_uri AS face_crop_uri,
                    processing_results.core_result_json AS core_result_json,
                    processing_results.error_code AS error_code
                FROM uploads
                LEFT JOIN processing_results ON processing_results.upload_id = uploads.id
                WHERE uploads.user_id = ?
                ORDER BY uploads.created_at DESC, uploads.id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [_row_to_user_record(row) for row in rows]


def _row_to_user_record(row) -> UserRecord:
    return UserRecord(
        upload_id=int(row["upload_id"]),
        user_id=int(row["user_id"]),
        filename=row["filename"],
        mime_type=row["mime_type"],
        source_ref=row["source_ref"],
        upload_status=UploadStatus(row["upload_status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"])
            if row["completed_at"] is not None
            else None
        ),
        is_passport=_nullable_bool(row["is_passport"]),
        has_face=_nullable_bool(row["has_face"]),
        is_complete=_nullable_bool(row["is_complete"]),
        passport_number=row["passport_number"],
        passport_image_uri=row["passport_image_uri"],
        face_crop_uri=row["face_crop_uri"],
        core_result=_parse_core_result(row["core_result_json"]),
        error_code=row["error_code"],
    )


def _nullable_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _parse_core_result(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    return json.loads(value)
