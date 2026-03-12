from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from passport_platform.db import Database
from passport_platform.enums import PlanName, UploadStatus, UsageEventType, UserStatus
from passport_platform.schemas.results import MonthlyUsageReport, RecentUploadRecord


@dataclass(slots=True)
class UsageCounts:
    upload_count: int
    success_count: int
    failure_count: int


class ReportingRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get_usage_counts(
        self,
        *,
        user_id: int,
        period_start: datetime,
        period_end: datetime,
    ) -> UsageCounts:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT event_type, COALESCE(SUM(units), 0) AS total_units
                FROM usage_ledger
                WHERE user_id = ?
                  AND created_at >= ?
                  AND created_at < ?
                GROUP BY event_type
                """,
                (user_id, period_start.isoformat(), period_end.isoformat()),
            ).fetchall()

        totals = {row["event_type"]: int(row["total_units"] or 0) for row in rows}
        return UsageCounts(
            upload_count=totals.get(UsageEventType.UPLOAD_RECEIVED.value, 0),
            success_count=totals.get(UsageEventType.SUCCESSFUL_PROCESS.value, 0),
            failure_count=totals.get(UsageEventType.FAILED_PROCESS.value, 0),
        )

    def get_monthly_usage_report(
        self,
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> MonthlyUsageReport:
        with self.db.connect() as conn:
            user_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_users,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS active_users,
                    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS blocked_users
                FROM users
                """,
                (UserStatus.ACTIVE.value, UserStatus.BLOCKED.value),
            ).fetchone()
            usage_rows = conn.execute(
                """
                SELECT event_type, COALESCE(SUM(units), 0) AS total_units
                FROM usage_ledger
                WHERE created_at >= ?
                  AND created_at < ?
                GROUP BY event_type
                """,
                (period_start.isoformat(), period_end.isoformat()),
            ).fetchall()

        usage_totals = {row["event_type"]: int(row["total_units"] or 0) for row in usage_rows}
        return MonthlyUsageReport(
            period_start=period_start,
            period_end=period_end,
            total_users=int(user_row["total_users"] or 0),
            active_users=int(user_row["active_users"] or 0),
            blocked_users=int(user_row["blocked_users"] or 0),
            total_uploads=usage_totals.get(UsageEventType.UPLOAD_RECEIVED.value, 0),
            total_successes=usage_totals.get(UsageEventType.SUCCESSFUL_PROCESS.value, 0),
            total_failures=usage_totals.get(UsageEventType.FAILED_PROCESS.value, 0),
        )

    def list_recent_uploads(self, *, limit: int = 10) -> list[RecentUploadRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    uploads.id AS upload_id,
                    uploads.user_id AS user_id,
                    users.external_provider AS external_provider,
                    users.external_user_id AS external_user_id,
                    users.display_name AS display_name,
                    users.plan AS plan,
                    users.status AS user_status,
                    uploads.filename AS filename,
                    uploads.source_ref AS source_ref,
                    uploads.status AS upload_status,
                    processing_results.passport_number AS passport_number,
                    processing_results.error_code AS error_code,
                    uploads.created_at AS created_at,
                    processing_results.completed_at AS completed_at
                FROM uploads
                JOIN users ON users.id = uploads.user_id
                LEFT JOIN processing_results ON processing_results.upload_id = uploads.id
                ORDER BY uploads.created_at DESC, uploads.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_recent_upload(row) for row in rows]


def _row_to_recent_upload(row) -> RecentUploadRecord:
    return RecentUploadRecord(
        upload_id=int(row["upload_id"]),
        user_id=int(row["user_id"]),
        external_provider=row["external_provider"],
        external_user_id=row["external_user_id"],
        display_name=row["display_name"],
        plan=PlanName(row["plan"]),
        user_status=UserStatus(row["user_status"]),
        filename=row["filename"],
        source_ref=row["source_ref"],
        upload_status=UploadStatus(row["upload_status"]),
        passport_number=row["passport_number"],
        error_code=row["error_code"],
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"])
            if row["completed_at"] is not None
            else None
        ),
    )
