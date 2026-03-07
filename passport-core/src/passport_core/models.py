from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class PassportData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    PassportNumber: str | None = None
    CountryCode: str | None = None
    MrzLine1: str | None = None
    MrzLine2: str | None = None
    SurnameAr: str | None = None
    GivenNamesAr: str | None = None
    SurnameEn: str | None = None
    GivenNamesEn: str | None = None
    DateOfBirth: str | None = None
    PlaceOfBirthAr: str | None = None
    PlaceOfBirthEn: str | None = None
    Sex: str | None = None
    DateOfIssue: str | None = None
    DateOfExpiry: str | None = None
    ProfessionAr: str | None = None
    ProfessionEn: str | None = None
    IssuingAuthorityAr: str | None = None
    IssuingAuthorityEn: str | None = None


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


class PassportProcessingResult(BaseModel):
    source: str
    stored_original_uri: str | None = None
    stored_aligned_uri: str | None = None
    validation: ValidationResult = Field(default_factory=lambda: ValidationResult(is_passport=False))
    face: FaceDetectionResult | None = None
    data: PassportData | None = None
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
