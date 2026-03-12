from __future__ import annotations

from dataclasses import dataclass

from passport_platform.enums import PlanName


@dataclass(slots=True, frozen=True)
class PlanPolicy:
    name: PlanName
    monthly_upload_limit: int
    monthly_success_limit: int
    max_batch_size: int
