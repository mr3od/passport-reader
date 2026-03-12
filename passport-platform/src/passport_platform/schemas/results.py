from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from passport_platform.enums import PlanName, UploadStatus, UserStatus
from passport_platform.models.upload import ProcessingResult, Upload
from passport_platform.models.user import User

if TYPE_CHECKING:
    from passport_core.workflow import PassportWorkflowResult
else:
    PassportWorkflowResult = Any


@dataclass(slots=True)
class QuotaDecision:
    allowed: bool
    plan: PlanName
    monthly_upload_limit: int
    monthly_uploads_used: int
    monthly_success_limit: int
    monthly_successes_used: int
    remaining_uploads: int
    remaining_successes: int
    max_batch_size: int
    reason: str | None = None


@dataclass(slots=True)
class TrackedProcessingResult:
    user: User
    upload: Upload
    quota_decision: QuotaDecision
    workflow_result: PassportWorkflowResult
    processing_result: ProcessingResult


@dataclass(slots=True)
class UserUsageReport:
    user: User
    quota_decision: QuotaDecision
    period_start: datetime
    period_end: datetime
    upload_count: int
    success_count: int
    failure_count: int


@dataclass(slots=True)
class MonthlyUsageReport:
    period_start: datetime
    period_end: datetime
    total_users: int
    active_users: int
    blocked_users: int
    total_uploads: int
    total_successes: int
    total_failures: int


@dataclass(slots=True)
class RecentUploadRecord:
    upload_id: int
    user_id: int
    external_provider: str
    external_user_id: str
    display_name: str | None
    plan: PlanName
    user_status: UserStatus
    filename: str
    source_ref: str
    upload_status: UploadStatus
    passport_number: str | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None
