from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class BroadcastContentType(StrEnum):
    TEXT = "text"
    PHOTO = "photo"


class BroadcastStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class Broadcast:
    id: int
    created_by_external_user_id: str
    content_type: BroadcastContentType
    text_body: str | None
    caption: str | None
    artifact_path: str | None
    status: BroadcastStatus
    total_targets: int
    sent_count: int
    failed_count: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
