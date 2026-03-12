from __future__ import annotations

from enum import StrEnum


class PlanName(StrEnum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"


class UserStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class UploadStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class UsageEventType(StrEnum):
    UPLOAD_RECEIVED = "upload_received"
    SUCCESSFUL_PROCESS = "successful_process"
    FAILED_PROCESS = "failed_process"


class ExternalProvider(StrEnum):
    TELEGRAM = "telegram"
    API = "api"


class ChannelName(StrEnum):
    TELEGRAM = "telegram"
    API = "api"
