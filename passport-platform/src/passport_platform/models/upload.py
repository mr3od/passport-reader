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
    has_face: bool
    is_complete: bool
    passport_number: str | None
    passport_image_uri: str | None
    face_crop_uri: str | None
    core_result_json: str | None
    error_code: str | None
    completed_at: datetime
