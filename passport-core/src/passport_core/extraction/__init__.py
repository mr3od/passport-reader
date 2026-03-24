"""VLM-based passport extraction pipeline."""

from passport_core.extraction.confidence import compute_confidence
from passport_core.extraction.extractor import PassportExtractor
from passport_core.extraction.models import (
    Confidence,
    ExtractionResult,
    ImageMeta,
    PassportFields,
    Reasoning,
)

__all__ = [
    "Confidence",
    "ExtractionResult",
    "ImageMeta",
    "PassportExtractor",
    "PassportFields",
    "Reasoning",
    "compute_confidence",
]
