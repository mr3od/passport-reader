from __future__ import annotations

from typing import TYPE_CHECKING

from passport_platform.models.user import User
from passport_platform.schemas.results import QuotaDecision
from passport_platform.strings import (
    AUTH_SESSION_INVALID,
    AUTH_TOKEN_INVALID,
    QUOTA_UPLOADS_EXCEEDED,
    USER_BLOCKED,
)

if TYPE_CHECKING:
    from passport_platform.schemas.results import TrackedProcessingResult


class PlatformError(Exception):
    """Base exception for shared platform services."""


class QuotaExceededError(PlatformError):
    def __init__(self, decision: QuotaDecision) -> None:
        self.decision = decision
        super().__init__(decision.reason or QUOTA_UPLOADS_EXCEEDED)


class UserBlockedError(PlatformError):
    def __init__(self, user: User) -> None:
        self.user = user
        super().__init__(USER_BLOCKED)


class UnsupportedExternalProviderError(PlatformError):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"unsupported external provider: {provider}")


class UnsupportedChannelError(PlatformError):
    def __init__(self, channel: str) -> None:
        self.channel = channel
        super().__init__(f"unsupported channel: {channel}")


class ProcessingFailedError(PlatformError):
    def __init__(self, result: TrackedProcessingResult, cause: Exception) -> None:
        self.result = result
        self.cause = cause
        super().__init__(f"processing failed for upload {result.upload.id}")


class InvalidTempTokenError(PlatformError):
    def __init__(self, reason: str = AUTH_TOKEN_INVALID) -> None:
        self.reason = reason
        super().__init__(reason)


class InvalidExtensionSessionError(PlatformError):
    def __init__(self, reason: str = AUTH_SESSION_INVALID) -> None:
        self.reason = reason
        super().__init__(reason)
