from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ExchangeTokenRequest(BaseModel):
    token: str


class ExchangeTokenResponse(BaseModel):
    session_token: str
    expires_at: datetime


class MeResponse(BaseModel):
    user_id: int
    external_provider: str
    external_user_id: str
    display_name: str | None
    plan: str
    status: str


class RecordResponse(BaseModel):
    upload_id: int
    user_id: int
    filename: str
    mime_type: str
    source_ref: str
    upload_status: str
    created_at: datetime
    completed_at: datetime | None
    is_passport: bool | None
    has_face: bool | None
    is_complete: bool | None
    passport_number: str | None
    passport_image_uri: str | None
    face_crop_uri: str | None
    core_result: dict[str, Any] | None
    error_code: str | None
    masar_status: str | None


class MasarStatusUpdate(BaseModel):
    status: str
    masar_mutamer_id: str | None = None
    masar_scan_result: dict[str, Any] | None = None
