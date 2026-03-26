from __future__ import annotations

import json
from datetime import UTC, datetime

from passport_platform.db import Database
from passport_platform.enums import UploadStatus
from passport_platform.schemas.results import UserRecord

_LATEST_MASAR_SUBMISSION_JOIN = """
LEFT JOIN (
    SELECT
        ms1.upload_id AS upload_id,
        ms1.status AS masar_status,
        ms1.mutamer_id AS masar_mutamer_id,
        ms1.scan_result_json AS masar_scan_result_json
    FROM masar_submissions ms1
    INNER JOIN (
        SELECT upload_id, MAX(id) AS max_id
        FROM masar_submissions
        GROUP BY upload_id
    ) ms2 ON ms1.id = ms2.max_id
) ms ON ms.upload_id = uploads.id
"""

_USER_RECORD_COLUMNS = """
    uploads.id AS upload_id,
    uploads.user_id AS user_id,
    uploads.filename AS filename,
    uploads.mime_type AS mime_type,
    uploads.source_ref AS source_ref,
    uploads.status AS upload_status,
    uploads.created_at AS created_at,
    processing_results.completed_at AS completed_at,
    processing_results.is_passport AS is_passport,
    processing_results.is_complete AS is_complete,
    processing_results.review_status AS review_status,
    processing_results.reviewed_by_user_id AS reviewed_by_user_id,
    processing_results.reviewed_at AS reviewed_at,
    processing_results.passport_number AS passport_number,
    processing_results.passport_image_uri AS passport_image_uri,
    processing_results.confidence_overall AS confidence_overall,
    processing_results.extraction_result_json AS extraction_result_json,
    processing_results.error_code AS error_code,
    ms.masar_status AS masar_status,
    ms.masar_mutamer_id AS masar_mutamer_id,
    ms.masar_scan_result_json AS masar_scan_result_json
"""


class RecordsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list_user_records(self, user_id: int, *, limit: int = 50) -> list[UserRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    {_USER_RECORD_COLUMNS}
                FROM uploads
                LEFT JOIN processing_results ON processing_results.upload_id = uploads.id
                {_LATEST_MASAR_SUBMISSION_JOIN}
                WHERE uploads.user_id = ?
                ORDER BY uploads.created_at DESC, uploads.id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [_row_to_user_record(row) for row in rows]

    def get_masar_pending(self, user_id: int) -> list[UserRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    {_USER_RECORD_COLUMNS}
                FROM uploads
                INNER JOIN processing_results ON processing_results.upload_id = uploads.id
                {_LATEST_MASAR_SUBMISSION_JOIN}
                WHERE uploads.user_id = ?
                  AND processing_results.is_complete = 1
                  AND (ms.masar_status IS NULL OR ms.masar_status = 'failed')
                ORDER BY uploads.created_at ASC, uploads.id ASC
                """,
                (user_id,),
            ).fetchall()
        return [_row_to_user_record(row) for row in rows]

    def get_user_record(self, user_id: int, upload_id: int) -> UserRecord | None:
        with self.db.connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    {_USER_RECORD_COLUMNS}
                FROM uploads
                LEFT JOIN processing_results ON processing_results.upload_id = uploads.id
                {_LATEST_MASAR_SUBMISSION_JOIN}
                WHERE uploads.user_id = ? AND uploads.id = ?
                """,
                (user_id, upload_id),
            ).fetchone()
        return _row_to_user_record(row) if row else None

    def insert_masar_submission(
        self,
        *,
        upload_id: int,
        user_id: int,
        status: str,
        masar_mutamer_id: str | None,
        masar_scan_result_json: str | None,
    ) -> bool:
        created_at = datetime.now(UTC)
        submitted_at = created_at if status == "submitted" else None
        with self.db.connect() as conn:
            upload_row = conn.execute(
                "SELECT id FROM uploads WHERE id = ? AND user_id = ?",
                (upload_id, user_id),
            ).fetchone()
            if upload_row is None:
                return False
            conn.execute(
                """
                INSERT INTO masar_submissions (
                    upload_id,
                    status,
                    mutamer_id,
                    scan_result_json,
                    submitted_at,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    status,
                    masar_mutamer_id,
                    masar_scan_result_json,
                    submitted_at.isoformat() if submitted_at is not None else None,
                    created_at.isoformat(),
                ),
            )
            conn.commit()
        return True

    def mark_reviewed(self, *, upload_id: int, user_id: int) -> bool:
        reviewed_at = datetime.now(UTC).isoformat()
        with self.db.connect() as conn:
            result = conn.execute(
                """
                UPDATE processing_results
                SET review_status = 'reviewed',
                    reviewed_by_user_id = ?,
                    reviewed_at = ?
                WHERE upload_id = ?
                  AND review_status = 'needs_review'
                  AND upload_id IN (
                      SELECT id FROM uploads WHERE user_id = ?
                  )
                """,
                (user_id, reviewed_at, upload_id, user_id),
            )
            conn.commit()
        return result.rowcount > 0


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
            datetime.fromisoformat(row["completed_at"]) if row["completed_at"] is not None else None
        ),
        is_passport=_nullable_bool(row["is_passport"]),
        is_complete=_nullable_bool(row["is_complete"]),
        review_status=row["review_status"],
        reviewed_by_user_id=row["reviewed_by_user_id"],
        reviewed_at=(
            datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] is not None else None
        ),
        passport_number=row["passport_number"],
        passport_image_uri=row["passport_image_uri"],
        confidence_overall=row["confidence_overall"],
        extraction_result=_parse_json(row["extraction_result_json"]),
        error_code=row["error_code"],
        masar_status=row["masar_status"],
        masar_mutamer_id=row["masar_mutamer_id"],
        masar_scan_result=_parse_json(row["masar_scan_result_json"]),
    )


def _nullable_bool(value: object | None) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _parse_json(value: str | None) -> dict[str, object] | None:
    if not value:
        return None
    loaded = json.loads(value)
    if not isinstance(loaded, dict):
        return None
    return loaded
