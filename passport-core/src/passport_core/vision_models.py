"""Validation and face-detection models used by the image-processing pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int
    score: float | None = None


class ValidationDebug(BaseModel):
    good_matches: int = 0
    inliers: int = 0
    inlier_ratio: float = 0.0
    score: float = 0.0


class ValidationResult(BaseModel):
    is_passport: bool = False
    page_quad: list[tuple[int, int]] | None = None
    debug: ValidationDebug = Field(default_factory=ValidationDebug)


class FaceDetectionResult(BaseModel):
    bbox_aligned: BoundingBox | None = None
    bbox_original: BoundingBox | None = None
    landmarks_original: list[tuple[int, int]] | None = None


class FaceCropResult(BaseModel):
    bbox_original: BoundingBox
    width: int
    height: int
    jpeg_bytes: bytes
