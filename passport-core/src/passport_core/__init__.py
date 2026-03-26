"""Core passport processing engine."""

from __future__ import annotations

import warnings

__version__ = "0.2.0"

from passport_core.config import Settings
from passport_core.io import LoadedImage

# Re-export legacy v1 API without triggering deprecation warnings at package level.
# Direct imports of passport_core.models / passport_core.workflow / passport_core.llm
# will still warn.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from passport_core.models import (
        BoundingBox,
        FaceCropResult,
        FaceDetectionResult,
        PassportData,
        ValidationResult,
    )
    from passport_core.workflow import PassportWorkflow, PassportWorkflowResult

__all__ = [
    "BoundingBox",
    "FaceCropResult",
    "FaceDetectionResult",
    "LoadedImage",
    "PassportData",
    "PassportWorkflow",
    "PassportWorkflowResult",
    "Settings",
    "ValidationResult",
]
