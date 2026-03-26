"""Core passport processing engine."""

from __future__ import annotations

__version__ = "0.3.0"

from passport_core.config import Settings
from passport_core.extraction import (
    Confidence,
    ExtractionResult,
    ImageMeta,
    PassportExtractor,
    PassportFields,
)
from passport_core.io import LoadedImage
from passport_core.vision_models import (
    BoundingBox,
    FaceCropResult,
    FaceDetectionResult,
    ValidationResult,
)

__all__ = [
    "BoundingBox",
    "Confidence",
    "ExtractionResult",
    "FaceCropResult",
    "FaceDetectionResult",
    "ImageMeta",
    "LoadedImage",
    "PassportExtractor",
    "PassportFields",
    "Settings",
    "ValidationResult",
]
