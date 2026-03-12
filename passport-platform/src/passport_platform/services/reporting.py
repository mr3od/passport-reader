from __future__ import annotations

from datetime import UTC, datetime

from passport_platform.repositories.reporting import ReportingRepository
from passport_platform.schemas.results import (
    MonthlyUsageReport,
    RecentUploadRecord,
    UserUsageReport,
)
from passport_platform.services.quotas import QuotaService
from passport_platform.services.users import UserService


class ReportingService:
    def __init__(
        self,
        *,
        users: UserService,
        quotas: QuotaService,
        reporting: ReportingRepository,
    ) -> None:
        self.users = users
        self.quotas = quotas
        self.reporting = reporting

    def get_user_usage_report(
        self,
        user_id: int,
        *,
        at: datetime | None = None,
    ) -> UserUsageReport:
        user = self.users.get_by_id(user_id)
        if user is None:
            raise KeyError(f"user {user_id} not found")
        now = at.astimezone(UTC) if at is not None else datetime.now(UTC)
        period_start, period_end = _month_window(now)
        counts = self.reporting.get_usage_counts(
            user_id=user.id,
            period_start=period_start,
            period_end=period_end,
        )
        quota = self.quotas.evaluate_user_quota(user, at=now)
        return UserUsageReport(
            user=user,
            quota_decision=quota,
            period_start=period_start,
            period_end=period_end,
            upload_count=counts.upload_count,
            success_count=counts.success_count,
            failure_count=counts.failure_count,
        )

    def get_monthly_usage_report(
        self,
        *,
        at: datetime | None = None,
    ) -> MonthlyUsageReport:
        now = at.astimezone(UTC) if at is not None else datetime.now(UTC)
        period_start, period_end = _month_window(now)
        return self.reporting.get_monthly_usage_report(
            period_start=period_start,
            period_end=period_end,
        )

    def list_recent_uploads(self, *, limit: int = 10) -> list[RecentUploadRecord]:
        return self.reporting.list_recent_uploads(limit=limit)


def _month_window(timestamp: datetime) -> tuple[datetime, datetime]:
    start = timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if timestamp.month == 12:
        end = start.replace(year=timestamp.year + 1, month=1)
    else:
        end = start.replace(month=timestamp.month + 1)
    return start, end
