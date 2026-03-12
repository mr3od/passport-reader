from __future__ import annotations

from passport_platform.schemas.results import QuotaDecision


class PlatformError(Exception):
    """Base exception for shared platform services."""


class QuotaExceededError(PlatformError):
    def __init__(self, decision: QuotaDecision) -> None:
        self.decision = decision
        super().__init__(decision.reason or "quota exceeded")
