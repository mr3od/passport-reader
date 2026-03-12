from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from passport_platform.enums import ExternalProvider, PlanName, UserStatus


@dataclass(slots=True)
class User:
    id: int
    external_provider: ExternalProvider
    external_user_id: str
    display_name: str | None
    plan: PlanName
    status: UserStatus
    created_at: datetime
