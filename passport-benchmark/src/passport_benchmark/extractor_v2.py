"""Experimental v2 passport extractor with multi-step prompt.

Once validated via benchmarks, move this to ``passport_core.extractor``.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, BinaryContent, PromptedOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage

from passport_benchmark.compare import cross_validate
from passport_benchmark.prompt_v2 import EXTRACTION_PROMPT_V2

_DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_MRZ_ALLOWED_CHARS = re.compile(r"[^A-Z0-9<]")
_PLACEHOLDER_ONLY_PATTERN = re.compile(r"^[-_./\\|]+$")


# ── Output models ────────────────────────────────────────────────


class Reasoning(BaseModel):
    """Structured reasoning trace from extraction steps."""

    step1_assessment: str | None = None
    step6_mrz_viz_discrepancies: str | None = None
    step7_ar_en_consistency: str | None = None


class ImageMeta(BaseModel):
    """Scene-level image assessment returned by the extractor."""

    is_passport: bool | None = None
    orientation: str | None = None
    image_type: str | None = None
    layout: str | None = None
    image_quality: str | None = None
    mirrored: bool | None = None
    skew_level: str | None = None
    reasoning: str | None = None


class Confidence(BaseModel):
    """Model-reported confidence values."""

    overall: float | None = None
    fields: dict[str, float] = Field(default_factory=dict)


class PassportFields(BaseModel):
    """All extractable passport fields (matches passport_core.models.PassportData)."""

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


class AgentPassportOutput(PassportFields):
    """Raw structured output expected from the model."""

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


# ── Normalization ────────────────────────────────────────────────


def _clean_mrz(value: str) -> str:
    return _MRZ_ALLOWED_CHARS.sub("", value.upper())


def _normalize_text_value(value: str) -> str | None:
    value = value.strip()
    if value == "" or value.upper() in ("NULL", "N/A"):
        return None
    if _PLACEHOLDER_ONLY_PATTERN.fullmatch(value):
        return None
    return value


def _normalize_meta(meta: ImageMeta | None) -> ImageMeta | None:
    if meta is None:
        return None

    updates: dict[str, Any] = {}
    for field_name in ImageMeta.model_fields:
        value = getattr(meta, field_name)
        if isinstance(value, str):
            normalized = _normalize_text_value(value)
            updates[field_name] = normalized.lower() if normalized is not None else None
        else:
            updates[field_name] = value
    return meta.model_copy(update=updates)


def _compute_confidence(
    data: PassportFields,
    meta: ImageMeta | None,
    warnings: list[str],
) -> Confidence:
    """Compute confidence programmatically from image metadata and cross-validation.

    Starts every field at 1.0 and applies penalty caps based on:
    1. Image properties (orientation, quality, mirroring, skew)
    2. Cross-validation warnings (MRZ vs VIZ discrepancies, check digit failures)
    3. Field presence (null fields get 0.0)
    """
    all_field_names = set(PassportFields.model_fields)
    mrz_fields = {"PassportNumber", "MrzLine1", "MrzLine2", "DateOfBirth", "DateOfExpiry", "Sex"}

    fields = {f: 1.0 for f in all_field_names}

    def _cap(field_names: set[str], cap: float) -> None:
        for f in field_names:
            fields[f] = min(fields[f], cap)

    # ── Image metadata penalties ──
    if meta is not None:
        if meta.mirrored is True:
            _cap(all_field_names, 0.35)

        orientation_caps = {"rotated_90": 0.7, "rotated_180": 0.7, "rotated_270": 0.7}
        orientation_cap = orientation_caps.get(meta.orientation or "")
        if orientation_cap is not None:
            _cap(all_field_names, orientation_cap)
            _cap(mrz_fields, 0.6)

        skew_caps = {"mild": 0.85, "severe": 0.6}
        skew_cap = skew_caps.get(meta.skew_level or "")
        if skew_cap is not None:
            _cap(all_field_names, skew_cap)

        quality_caps = {"fair": 0.9, "poor": 0.65}
        quality_cap = quality_caps.get(meta.image_quality or "")
        if quality_cap is not None:
            _cap(all_field_names, quality_cap)

    # ── Cross-validation warning penalties ──
    for warning in warnings:
        if warning.startswith("Check digit failures"):
            _cap(mrz_fields, 0.3)
        elif warning.startswith("PassportNumber:"):
            _cap({"PassportNumber", "MrzLine2"}, 0.2)
        elif warning.startswith("DOB:"):
            _cap({"DateOfBirth", "MrzLine2"}, 0.2)
        elif warning.startswith("Expiry:"):
            _cap({"DateOfExpiry", "MrzLine2"}, 0.2)
        elif warning.startswith("Sex:"):
            _cap({"Sex", "MrzLine2"}, 0.2)
        elif warning.startswith("Given name tokens:"):
            _cap({"GivenNameTokensAr", "GivenNameTokensEn"}, 0.4)
        elif warning.startswith("SurnameEn:"):
            _cap({"SurnameEn", "MrzLine1"}, 0.4)
        elif warning.startswith("GivenNameTokensEn:"):
            _cap({"GivenNameTokensEn", "MrzLine1"}, 0.4)
        elif "rebuild mismatch" in warning:
            if "MrzLine1" in warning:
                _cap({"MrzLine1"}, 0.5)
            elif "MrzLine2" in warning:
                _cap({"MrzLine2"}, 0.5)

    # ── Null field penalty: no value = no confidence ──
    for field_name in all_field_names:
        value = getattr(data, field_name)
        if value is None or (isinstance(value, list) and not value):
            fields[field_name] = 0.0

    overall = sum(v for v in fields.values() if v > 0.0)
    non_null_count = sum(1 for v in fields.values() if v > 0.0)
    overall = overall / non_null_count if non_null_count else 0.0

    return Confidence(overall=overall, fields=fields)


def _normalize_token_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw_tokens = value.split()
    elif isinstance(value, list):
        raw_tokens = value
    else:
        return None

    tokens: list[str] = []
    for token in raw_tokens:
        if not isinstance(token, str):
            continue
        normalized = _normalize_text_value(token)
        if normalized is not None:
            tokens.append(normalized)
    return tokens or None


def _apply_name_token_fields(updates: dict[str, Any]) -> None:
    for language in ("Ar", "En"):
        tokens_key = f"GivenNameTokens{language}"
        token_list = _normalize_token_list(updates.get(tokens_key))
        updates[tokens_key] = token_list


def _canonicalize_mrz_line1(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _clean_mrz(value).rstrip("<")
    if cleaned == "":
        return None
    if len(cleaned) <= 5:
        return cleaned.ljust(44, "<")
    return (cleaned[:5] + cleaned[5:39 + 5]).ljust(44, "<")


def _canonicalize_mrz_line2(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _clean_mrz(value)
    if cleaned == "":
        return None
    if len(cleaned) <= 28:
        return cleaned.ljust(44, "<")

    prefix = cleaned[:28]
    tail = cleaned[28:]
    if len(tail) >= 2:
        trailing_checks = tail[-2:]
        optional_data = tail[:-2]
    else:
        trailing_checks = tail.ljust(2, "<")
        optional_data = ""

    optional_data = optional_data.rstrip("<").ljust(14, "<")[:14]
    return prefix + optional_data + trailing_checks


def _usage_dict(usage: RunUsage) -> dict[str, int]:
    data = asdict(usage)
    total_tokens = sum(
        value
        for key, value in data.items()
        if key.endswith("_tokens") and isinstance(value, int)
    )
    details = data.pop("details", {})
    usage_data = {key: value for key, value in data.items() if isinstance(value, int)}
    usage_data["total_tokens"] = total_tokens
    for key, value in details.items():
        usage_data[f"detail_{key}"] = value
    return usage_data


def _normalize(data: PassportFields) -> PassportFields:
    updates: dict[str, Any] = {}
    for field_name in PassportFields.model_fields:
        value = getattr(data, field_name)
        if isinstance(value, str):
            value = _normalize_text_value(value)
        updates[field_name] = value

    for date_field in ("DateOfBirth", "DateOfIssue", "DateOfExpiry"):
        val = updates.get(date_field)
        if val is not None and not _DATE_PATTERN.fullmatch(val):
            updates[date_field] = None

    _apply_name_token_fields(updates)
    updates["MrzLine1"] = _canonicalize_mrz_line1(updates.get("MrzLine1"))
    updates["MrzLine2"] = _canonicalize_mrz_line2(updates.get("MrzLine2"))
    updates["Sex"] = updates["Sex"] if updates.get("Sex") in {"M", "F"} else None

    return data.model_copy(update=updates)


# ── Extractor ────────────────────────────────────────────────────


class PassportExtractorV2:
    """Multi-step passport extractor with reasoning trace and MRZ cross-validation."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self._agent = Agent(
            model=OpenAIChatModel(
                model,
                provider=OpenAIProvider(base_url=base_url, api_key=api_key),
            ),
            instructions=EXTRACTION_PROMPT_V2,
            output_type=PromptedOutput(AgentPassportOutput),
            retries=2,
        )

    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> ExtractionResult:
        result = self._agent.run_sync(
            [
                "Extract passport fields from this image following all 7 steps and return JSON.",
                BinaryContent(data=image_bytes, media_type=mime_type),
            ]
        )
        raw = result.output
        if not isinstance(raw, AgentPassportOutput):
            msg = "PydanticAI did not return AgentPassportOutput."
            raise ValueError(msg)

        data = _normalize(
            PassportFields.model_validate(
                raw.model_dump(exclude={"meta", "reasoning"})
            )
        )
        meta = _normalize_meta(raw.meta)
        warnings = cross_validate(data.model_dump())
        usage = _usage_dict(result.usage())
        confidence = _compute_confidence(data, meta, warnings)
        message_history_json = result.all_messages_json().decode("utf-8")

        return ExtractionResult(
            data=data,
            meta=meta,
            reasoning=raw.reasoning,
            confidence=confidence,
            warnings=warnings,
            usage=usage,
            message_history_json=message_history_json,
        )
