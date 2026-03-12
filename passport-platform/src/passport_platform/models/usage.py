from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from passport_platform.enums import UsageEventType


@dataclass(slots=True)
class UsageLedgerEntry:
    id: int
    user_id: int
    upload_id: int | None
    event_type: UsageEventType
    units: int
    created_at: datetime


@dataclass(slots=True)
class UsageSummary:
    user_id: int
    upload_units: int
    success_units: int
