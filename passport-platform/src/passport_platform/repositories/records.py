from __future__ import annotations

import json
from datetime import UTC, datetime

from passport_platform.db import Database
from passport_platform.enums import UploadStatus
from passport_platform.schemas.results import (
    UserRecord,
    UserRecordCounts,
    UserRecordIdItem,
    UserRecordIdListResult,
    UserRecordListItem,
    UserRecordListResult,
)

_LATEST_MASAR_SUBMISSION_JOIN = """
LEFT JOIN (
    SELECT
        ms1.upload_id AS upload_id,
        ms1.status AS masar_status,
        ms1.mutamer_id AS masar_mutamer_id,
        ms1.scan_result_json AS masar_scan_result_json,
        ms1.masar_detail_id AS masar_detail_id,
        ms1.submission_entity_id AS submission_entity_id,
        ms1.submission_entity_type_id AS submission_entity_type_id,
        ms1.submission_entity_name AS submission_entity_name,
        ms1.submission_contract_id AS submission_contract_id,
        ms1.submission_contract_name AS submission_contract_name,
        ms1.submission_contract_name_ar AS submission_contract_name_ar,
        ms1.submission_contract_name_en AS submission_contract_name_en,
        ms1.submission_contract_number AS submission_contract_number,
        ms1.submission_contract_status AS submission_contract_status,
        ms1.submission_uo_subscription_status_id AS submission_uo_subscription_status_id,
        ms1.submission_group_id AS submission_group_id,
        ms1.submission_group_name AS submission_group_name,
        ms1.submission_group_number AS submission_group_number,
        ms1.failure_reason_code AS failure_reason_code,
        ms1.failure_reason_text AS failure_reason_text
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
    uploads.archived_at AS archived_at,
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
    ms.masar_scan_result_json AS masar_scan_result_json,
    ms.masar_detail_id AS masar_detail_id,
    ms.submission_entity_id AS submission_entity_id,
    ms.submission_entity_type_id AS submission_entity_type_id,
    ms.submission_entity_name AS submission_entity_name,
    ms.submission_contract_id AS submission_contract_id,
    ms.submission_contract_name AS submission_contract_name,
    ms.submission_contract_name_ar AS submission_contract_name_ar,
    ms.submission_contract_name_en AS submission_contract_name_en,
    ms.submission_contract_number AS submission_contract_number,
    ms.submission_contract_status AS submission_contract_status,
    ms.submission_uo_subscription_status_id AS submission_uo_subscription_status_id,
    ms.submission_group_id AS submission_group_id,
    ms.submission_group_name AS submission_group_name,
    ms.submission_group_number AS submission_group_number,
    ms.failure_reason_code AS failure_reason_code,
    ms.failure_reason_text AS failure_reason_text
"""

_USER_RECORD_LIST_COLUMNS = """
    uploads.id AS upload_id,
    uploads.filename AS filename,
    uploads.status AS upload_status,
    uploads.created_at AS created_at,
    uploads.archived_at AS archived_at,
    processing_results.completed_at AS completed_at,
    processing_results.review_status AS review_status,
    processing_results.passport_number AS passport_number,
    processing_results.extraction_result_json AS extraction_result_json,
    ms.masar_status AS masar_status,
    ms.masar_detail_id AS masar_detail_id,
    ms.failure_reason_code AS failure_reason_code,
    ms.failure_reason_text AS failure_reason_text
"""

_USER_RECORD_ID_COLUMNS = """
    uploads.id AS upload_id,
    uploads.status AS upload_status,
    processing_results.review_status AS review_status,
    ms.masar_status AS masar_status
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

    def list_user_record_items(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
        section: str,
    ) -> UserRecordListResult:
        where_clause = _section_where_clause(section)
        order_by_clause = _section_order_by_clause(section)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    {_USER_RECORD_LIST_COLUMNS}
                FROM uploads
                LEFT JOIN processing_results ON processing_results.upload_id = uploads.id
                {_LATEST_MASAR_SUBMISSION_JOIN}
                WHERE uploads.user_id = ?
                  AND {where_clause}
                ORDER BY {order_by_clause}
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()
            total = conn.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM uploads
                LEFT JOIN processing_results ON processing_results.upload_id = uploads.id
                {_LATEST_MASAR_SUBMISSION_JOIN}
                WHERE uploads.user_id = ?
                  AND {where_clause}
                """,
                (user_id,),
            ).fetchone()
        total_count = int(total["total"]) if total is not None else 0
        items = [_row_to_user_record_list_item(row) for row in rows]
        return UserRecordListResult(
            items=items,
            total=total_count,
            has_more=offset + len(items) < total_count,
        )

    def count_user_record_sections(self, user_id: int) -> UserRecordCounts:
        with self.db.connect() as conn:
            pending = _count_for_where_clause(conn, user_id, _section_where_clause("pending"))
            submitted = _count_for_where_clause(conn, user_id, _section_where_clause("submitted"))
            failed = _count_for_where_clause(conn, user_id, _section_where_clause("failed"))
        return UserRecordCounts(
            pending=pending,
            submitted=submitted,
            failed=failed,
        )

    def set_archive_state(
        self,
        *,
        upload_id: int,
        user_id: int,
        archived: bool,
    ) -> bool:
        archived_at = datetime.now(UTC).isoformat()
        with self.db.connect() as conn:
            result = conn.execute(
                """
                UPDATE uploads
                SET archived_at = CASE
                    WHEN ? = 1 THEN COALESCE(archived_at, ?)
                    ELSE NULL
                END
                WHERE id = ?
                  AND user_id = ?
                """,
                (1 if archived else 0, archived_at, upload_id, user_id),
            )
            conn.commit()
        return result.rowcount > 0

    def list_submit_eligible_record_ids(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> UserRecordIdListResult:
        where_clause = _submit_eligible_where_clause()
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    {_USER_RECORD_ID_COLUMNS}
                FROM uploads
                LEFT JOIN processing_results ON processing_results.upload_id = uploads.id
                {_LATEST_MASAR_SUBMISSION_JOIN}
                WHERE uploads.user_id = ?
                  AND {where_clause}
                ORDER BY uploads.created_at DESC, uploads.id DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()
            total = conn.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM uploads
                LEFT JOIN processing_results ON processing_results.upload_id = uploads.id
                {_LATEST_MASAR_SUBMISSION_JOIN}
                WHERE uploads.user_id = ?
                  AND {where_clause}
                """,
                (user_id,),
            ).fetchone()
        total_count = int(total["total"]) if total is not None else 0
        items = [_row_to_user_record_id_item(row) for row in rows]
        return UserRecordIdListResult(
            items=items,
            total=total_count,
            has_more=offset + len(items) < total_count,
        )

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
                  AND uploads.archived_at IS NULL
                  AND (ms.masar_status IS NULL OR ms.masar_status IN ('failed', 'missing'))
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
        masar_detail_id: str | None = None,
        submission_entity_id: str | None = None,
        submission_entity_type_id: str | None = None,
        submission_entity_name: str | None = None,
        submission_contract_id: str | None = None,
        submission_contract_name: str | None = None,
        submission_contract_name_ar: str | None = None,
        submission_contract_name_en: str | None = None,
        submission_contract_number: str | None = None,
        submission_contract_status: bool | None = None,
        submission_uo_subscription_status_id: int | None = None,
        submission_group_id: str | None = None,
        submission_group_name: str | None = None,
        submission_group_number: str | None = None,
        failure_reason_code: str | None = None,
        failure_reason_text: str | None = None,
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
                    masar_detail_id,
                    submission_entity_id,
                    submission_entity_type_id,
                    submission_entity_name,
                    submission_contract_id,
                    submission_contract_name,
                    submission_contract_name_ar,
                    submission_contract_name_en,
                    submission_contract_number,
                    submission_contract_status,
                    submission_uo_subscription_status_id,
                    submission_group_id,
                    submission_group_name,
                    submission_group_number,
                    failure_reason_code,
                    failure_reason_text,
                    submitted_at,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    status,
                    masar_mutamer_id,
                    masar_scan_result_json,
                    masar_detail_id,
                    submission_entity_id,
                    submission_entity_type_id,
                    submission_entity_name,
                    submission_contract_id,
                    submission_contract_name,
                    submission_contract_name_ar,
                    submission_contract_name_en,
                    submission_contract_number,
                    (
                        1
                        if submission_contract_status is True
                        else 0
                        if submission_contract_status is False
                        else None
                    ),
                    submission_uo_subscription_status_id,
                    submission_group_id,
                    submission_group_name,
                    submission_group_number,
                    failure_reason_code,
                    failure_reason_text,
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
        archived_at=(
            datetime.fromisoformat(row["archived_at"]) if row["archived_at"] is not None else None
        ),
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
        masar_detail_id=row["masar_detail_id"],
        submission_entity_id=row["submission_entity_id"],
        submission_entity_type_id=row["submission_entity_type_id"],
        submission_entity_name=row["submission_entity_name"],
        submission_contract_id=row["submission_contract_id"],
        submission_contract_name=row["submission_contract_name"],
        submission_contract_name_ar=row["submission_contract_name_ar"],
        submission_contract_name_en=row["submission_contract_name_en"],
        submission_contract_number=row["submission_contract_number"],
        submission_contract_status=_nullable_bool(row["submission_contract_status"]),
        submission_uo_subscription_status_id=row["submission_uo_subscription_status_id"],
        submission_group_id=row["submission_group_id"],
        submission_group_name=row["submission_group_name"],
        submission_group_number=row["submission_group_number"],
        failure_reason_code=row["failure_reason_code"],
        failure_reason_text=row["failure_reason_text"],
    )


def _row_to_user_record_list_item(row) -> UserRecordListItem:
    full_name_ar, full_name_en = _list_item_names(row["extraction_result_json"])
    return UserRecordListItem(
        upload_id=int(row["upload_id"]),
        filename=row["filename"],
        upload_status=UploadStatus(row["upload_status"]),
        review_status=row["review_status"],
        masar_status=row["masar_status"],
        masar_detail_id=row["masar_detail_id"],
        passport_number=row["passport_number"],
        full_name_ar=full_name_ar,
        full_name_en=full_name_en,
        created_at=datetime.fromisoformat(row["created_at"]),
        archived_at=(
            datetime.fromisoformat(row["archived_at"]) if row["archived_at"] is not None else None
        ),
        completed_at=(
            datetime.fromisoformat(row["completed_at"]) if row["completed_at"] is not None else None
        ),
        failure_reason_code=row["failure_reason_code"],
        failure_reason_text=row["failure_reason_text"],
    )


def _row_to_user_record_id_item(row) -> UserRecordIdItem:
    return UserRecordIdItem(
        upload_id=int(row["upload_id"]),
        upload_status=UploadStatus(row["upload_status"]),
        review_status=row["review_status"],
        masar_status=row["masar_status"],
    )


def _count_for_where_clause(conn, user_id: int, where_clause: str) -> int:
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM uploads
        LEFT JOIN processing_results ON processing_results.upload_id = uploads.id
        {_LATEST_MASAR_SUBMISSION_JOIN}
        WHERE uploads.user_id = ?
          AND {where_clause}
        """,
        (user_id,),
    ).fetchone()
    return int(row["total"]) if row is not None else 0


def _section_where_clause(section: str) -> str:
    """Return the SQL predicate for a slim list section."""
    clauses = {
        "pending": """
            uploads.status = 'processed'
            AND ms.masar_status IS NULL
            AND uploads.archived_at IS NULL
        """,
        "submitted": """
            ms.masar_status = 'submitted'
            AND uploads.archived_at IS NULL
        """,
        "failed": """
            (
                uploads.status = 'failed'
                OR ms.masar_status IN ('failed', 'missing')
            )
            AND uploads.archived_at IS NULL
        """,
        "archived": "uploads.archived_at IS NOT NULL",
        "all": "1 = 1",
    }
    try:
        return clauses[section]
    except KeyError as exc:
        raise ValueError(f"unsupported record section: {section}") from exc


def _submit_eligible_where_clause() -> str:
    """Return the SQL predicate for bulk-submit discovery."""
    return """
        uploads.status = 'processed'
        AND ms.masar_status IS NULL
        AND uploads.archived_at IS NULL
    """


def _section_order_by_clause(section: str) -> str:
    if section == "archived":
        return "uploads.archived_at DESC, uploads.id DESC"
    return "uploads.created_at DESC, uploads.id DESC"


def _list_item_names(extraction_result_json: str | None) -> tuple[str | None, str | None]:
    extraction = _parse_json(extraction_result_json)
    raw_data = extraction.get("data") if isinstance(extraction, dict) else None
    if not isinstance(raw_data, dict):
        return None, None
    data = {key: value for key, value in raw_data.items() if isinstance(key, str)}
    full_name_ar = _join_values(
        _join_tokens(_string_list_value(data, "GivenNameTokensAr")),
        _string_value(data, "SurnameAr"),
    )
    full_name_en = _join_values(
        _join_tokens(_string_list_value(data, "GivenNameTokensEn")),
        _string_value(data, "SurnameEn"),
    )
    return full_name_ar, full_name_en


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


def _string_value(data: dict[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _string_list_value(data: dict[str, object], field_name: str) -> list[str]:
    value = data.get(field_name)
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _join_tokens(values: list[str]) -> str | None:
    if not values:
        return None
    return " ".join(values)


def _join_values(*values: str | None) -> str | None:
    normalized = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    if not normalized:
        return None
    return " ".join(normalized)
