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
    confidence: Confidence | None = Field(default=None, alias="_confidence")


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


def _normalize_confidence(confidence: Confidence | None) -> Confidence | None:
    if confidence is None:
        return None

    def _clamp(value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, min(1.0, value))

    allowed_fields = set(PassportFields.model_fields)
    normalized_fields: dict[str, float] = {}
    for key, value in confidence.fields.items():
        if key in allowed_fields and isinstance(value, (int, float)):
            normalized_fields[key] = _clamp(float(value)) or 0.0

    return confidence.model_copy(
        update={
            "overall": _clamp(confidence.overall),
            "fields": normalized_fields,
        }
    )


def _cap_confidence_fields(
    fields: dict[str, float],
    field_names: set[str],
    cap: float,
) -> dict[str, float]:
    updated = dict(fields)
    for field_name in field_names:
        if field_name in updated:
            updated[field_name] = min(updated[field_name], cap)
    return updated


def _apply_confidence_layer(
    confidence: Confidence | None,
    meta: ImageMeta | None,
    warnings: list[str],
) -> Confidence | None:
    if confidence is None:
        return None

    overall = confidence.overall
    fields = dict(confidence.fields)

    all_fields = set(PassportFields.model_fields)
    mrz_fields = {"PassportNumber", "MrzLine1", "MrzLine2", "DateOfBirth", "DateOfExpiry", "Sex"}

    if meta is not None:
        if meta.mirrored is True:
            overall = min(overall if overall is not None else 1.0, 0.35)
            fields = _cap_confidence_fields(fields, all_fields, 0.35)

        orientation_caps = {
            "rotated_90": 0.7,
            "rotated_180": 0.7,
            "rotated_270": 0.7,
        }
        orientation_cap = orientation_caps.get(meta.orientation or "")
        if orientation_cap is not None:
            overall = min(overall if overall is not None else 1.0, orientation_cap)
            fields = _cap_confidence_fields(fields, all_fields, orientation_cap)
            fields = _cap_confidence_fields(fields, mrz_fields, min(orientation_cap, 0.6))

        skew_caps = {
            "mild": 0.85,
            "severe": 0.6,
        }
        skew_cap = skew_caps.get(meta.skew_level or "")
        if skew_cap is not None:
            overall = min(overall if overall is not None else 1.0, skew_cap)
            fields = _cap_confidence_fields(fields, all_fields, skew_cap)

        quality_caps = {
            "fair": 0.9,
            "poor": 0.65,
        }
        quality_cap = quality_caps.get(meta.image_quality or "")
        if quality_cap is not None:
            overall = min(overall if overall is not None else 1.0, quality_cap)
            fields = _cap_confidence_fields(fields, all_fields, quality_cap)

    for warning in warnings:
        if warning.startswith("Check digit failures"):
            overall = min(overall if overall is not None else 1.0, 0.45)
            fields = _cap_confidence_fields(fields, mrz_fields, 0.3)
        elif warning.startswith("PassportNumber:"):
            fields = _cap_confidence_fields(fields, {"PassportNumber", "MrzLine2"}, 0.2)
        elif warning.startswith("DOB:"):
            fields = _cap_confidence_fields(fields, {"DateOfBirth", "MrzLine2"}, 0.2)
        elif warning.startswith("Expiry:"):
            fields = _cap_confidence_fields(fields, {"DateOfExpiry", "MrzLine2"}, 0.2)
        elif warning.startswith("Sex:"):
            fields = _cap_confidence_fields(fields, {"Sex", "MrzLine2"}, 0.2)
        elif warning.startswith("Given name tokens:"):
            fields = _cap_confidence_fields(fields, {"GivenNameTokensAr", "GivenNameTokensEn"}, 0.4)

    if overall is None and fields:
        overall = sum(fields.values()) / len(fields)
    elif overall is not None and fields:
        overall = min(overall, sum(fields.values()) / len(fields))

    return confidence.model_copy(update={"overall": overall, "fields": fields})


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
        confidence = _normalize_confidence(raw.confidence)
        warnings = cross_validate(data.model_dump())
        usage = _usage_dict(result.usage())
        confidence = _apply_confidence_layer(confidence, meta, warnings)
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
