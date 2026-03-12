from __future__ import annotations

from passport_platform.enums import PlanName
from passport_platform.models.plan import PlanPolicy

PLAN_POLICIES: dict[PlanName, PlanPolicy] = {
    PlanName.FREE: PlanPolicy(
        name=PlanName.FREE,
        monthly_upload_limit=20,
        monthly_success_limit=20,
        max_batch_size=2,
    ),
    PlanName.BASIC: PlanPolicy(
        name=PlanName.BASIC,
        monthly_upload_limit=300,
        monthly_success_limit=300,
        max_batch_size=10,
    ),
    PlanName.PRO: PlanPolicy(
        name=PlanName.PRO,
        monthly_upload_limit=3000,
        monthly_success_limit=3000,
        max_batch_size=25,
    ),
}


def get_plan_policy(plan: PlanName) -> PlanPolicy:
    return PLAN_POLICIES[plan]
