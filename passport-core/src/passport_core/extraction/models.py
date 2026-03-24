"""Data models for the extraction pipeline."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Reasoning(BaseModel):
    """Structured reasoning trace from extraction steps."""

    step1_assessment: str | None = None
    step6_mrz_viz_discrepancies: str | None = None
    step7_ar_en_consistency: str | None = None


class ImageMeta(BaseModel):
    """Scene-level image assessment returned by the VLM."""

    is_passport: bool | None = None
    orientation: str | None = None
    image_type: str | None = None
    layout: str | None = None
    image_quality: str | None = None
    mirrored: bool | None = None
    skew_level: str | None = None
    reasoning: str | None = None


class Confidence(BaseModel):
    """Programmatically computed confidence values."""

    overall: float | None = None
    fields: dict[str, float] = Field(default_factory=dict)


class PassportFields(BaseModel):
    """All extractable passport fields."""

    PassportNumber: str | None = None
    CountryCode: str | None = None
    MrzLine1: str | None = None
    MrzLine2: str | None = None
    SurnameAr: str | None = None
    GivenNameTokensAr: list[str] | None = None
    SurnameEn: str | None = None
    GivenNameTokensEn: list[str] | None = None
    DateOfBirth: str | None = None
    PlaceOfBirthAr: str | None = None
    PlaceOfBirthEn: str | None = None
    BirthCityAr: str | None = None
    BirthCityEn: str | None = None
    BirthCountryAr: str | None = None
    BirthCountryEn: str | None = None
    Sex: str | None = None
    DateOfIssue: str | None = None
    DateOfExpiry: str | None = None
    ProfessionAr: str | None = None
    ProfessionEn: str | None = None
    IssuingAuthorityAr: str | None = None
    IssuingAuthorityEn: str | None = None


class AgentOutput(PassportFields):
    """Raw structured output expected from the VLM (internal)."""

    model_config = ConfigDict(populate_by_name=True)

    meta: ImageMeta | None = Field(default=None, alias="_meta")
    reasoning: Reasoning | None = Field(default=None, alias="_reasoning")


class ExtractionResult(BaseModel):
    """Full extraction output with reasoning trace and validation warnings."""

    data: PassportFields
    meta: ImageMeta | None = None
    reasoning: Reasoning | None = None
    confidence: Confidence | None = None
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    message_history_json: str | None = None
