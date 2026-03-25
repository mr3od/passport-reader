from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from passport_platform.enums import UsageEventType
from passport_platform.errors import QuotaExceededError
from passport_platform.models.user import User
from passport_platform.policies.plans import get_plan_policy
from passport_platform.repositories.usage import UsageRepository
from passport_platform.schemas.results import QuotaDecision
from passport_platform.strings import QUOTA_SUCCESSES_EXCEEDED, QUOTA_UPLOADS_EXCEEDED


class QuotaService:
    def __init__(self, usage: UsageRepository) -> None:
        self.usage = usage

    def evaluate_user_quota(
        self,
        user: User,
        *,
        at: datetime | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> QuotaDecision:
        now = at.astimezone(UTC) if at is not None else datetime.now(UTC)
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = now.replace(year=now.year + 1, month=1, day=1)
        else:
            period_end = now.replace(month=now.month + 1, day=1)

        plan = get_plan_policy(user.plan)
        uploads_used = self.usage.sum_units_for_period(
            user_id=user.id,
            event_type=UsageEventType.UPLOAD_RECEIVED,
            period_start=period_start,
            period_end=period_end,
            conn=conn,
        )
        successes_used = self.usage.sum_units_for_period(
            user_id=user.id,
            event_type=UsageEventType.SUCCESSFUL_PROCESS,
            period_start=period_start,
            period_end=period_end,
            conn=conn,
        )
        remaining_uploads = max(plan.monthly_upload_limit - uploads_used, 0)
        remaining_successes = max(plan.monthly_success_limit - successes_used, 0)

        reason: str | None = None
        allowed = remaining_uploads > 0 and remaining_successes > 0
        if not allowed:
            reason = (
                QUOTA_UPLOADS_EXCEEDED
                if remaining_uploads == 0
                else QUOTA_SUCCESSES_EXCEEDED
            )

        return QuotaDecision(
            allowed=allowed,
            plan=user.plan,
            monthly_upload_limit=plan.monthly_upload_limit,
            monthly_uploads_used=uploads_used,
            monthly_success_limit=plan.monthly_success_limit,
            monthly_successes_used=successes_used,
            remaining_uploads=remaining_uploads,
            remaining_successes=remaining_successes,
            max_batch_size=plan.max_batch_size,
            reason=reason,
        )

    def assert_can_upload(
        self,
        user: User,
        *,
        at: datetime | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> QuotaDecision:
        decision = self.evaluate_user_quota(user, at=at, conn=conn)
        if not decision.allowed:
            raise QuotaExceededError(decision)
        return decision
