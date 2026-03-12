from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from passport_platform.enums import ChannelName, ExternalProvider, PlanName


@dataclass(slots=True)
class EnsureUserCommand:
    external_provider: ExternalProvider
    external_user_id: str
    display_name: str | None = None
    default_plan: PlanName = PlanName.FREE


@dataclass(slots=True)
class RegisterUploadCommand:
    user_id: int
    channel: ChannelName
    filename: str
    mime_type: str
    source_ref: str
    external_message_id: str | None = None
    external_file_id: str | None = None


@dataclass(slots=True)
class RecordProcessingResultCommand:
    upload_id: int
    is_passport: bool
    has_face: bool
    is_complete: bool
    passport_number: str | None = None
    error_code: str | None = None
    completed_at: datetime | None = None
