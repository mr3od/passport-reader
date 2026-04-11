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
    archived_at: datetime | None = None


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
    masar_detail_id: str | None
    submission_entity_id: str | None
    submission_entity_type_id: str | None
    submission_entity_name: str | None
    submission_contract_id: str | None
    submission_contract_name: str | None
    submission_contract_name_ar: str | None
    submission_contract_name_en: str | None
    submission_contract_number: str | None
    submission_contract_status: bool | None
    submission_uo_subscription_status_id: int | None
    submission_group_id: str | None
    submission_group_name: str | None
    submission_group_number: str | None
    failure_reason_code: str | None
    failure_reason_text: str | None
    submitted_at: datetime | None
    created_at: datetime
