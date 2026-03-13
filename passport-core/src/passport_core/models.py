from __future__ import annotations

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
    landmarks_original: list[tuple[int, int]] | None = None


class FaceCropResult(BaseModel):
    bbox_original: BoundingBox
    width: int
    height: int
    jpeg_bytes: bytes
