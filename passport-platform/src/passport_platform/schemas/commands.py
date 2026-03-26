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
    is_complete: bool
    review_status: str
    passport_number: str | None = None
    passport_image_uri: str | None = None
    confidence_overall: float | None = None
    extraction_result_json: str | None = None
    error_code: str | None = None
    completed_at: datetime | None = None


@dataclass(slots=True)
class ProcessUploadCommand:
    external_provider: ExternalProvider | str
    external_user_id: str
    channel: ChannelName | str
    filename: str
    mime_type: str
    source_ref: str
    payload: bytes
    display_name: str | None = None
    default_plan: PlanName = PlanName.FREE
    external_message_id: str | None = None
    external_file_id: str | None = None
