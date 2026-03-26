from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from passport_platform.enums import ChannelName, UploadStatus


@dataclass(slots=True)
class Upload:
    id: int
    user_id: int
    channel: ChannelName
    external_message_id: str | None
    external_file_id: str | None
    filename: str
    mime_type: str
    source_ref: str
    status: UploadStatus
    created_at: datetime


@dataclass(slots=True)
class ProcessingResult:
    id: int
    upload_id: int
    is_passport: bool
    is_complete: bool
    review_status: str
    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    passport_number: str | None
    passport_image_uri: str | None
    confidence_overall: float | None
    extraction_result_json: str | None
    error_code: str | None
    completed_at: datetime


@dataclass(slots=True)
class MasarSubmission:
    id: int
    upload_id: int
    status: str
    mutamer_id: str | None
    scan_result_json: str | None
    submitted_at: datetime | None
    created_at: datetime
