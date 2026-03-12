from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from passport_platform.enums import PlanName
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
