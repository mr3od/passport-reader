"""Normalization layer for extracted passport fields."""

from __future__ import annotations

import re
from typing import Any

from passport_core.extraction.models import ImageMeta, PassportFields

_DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_MRZ_ALLOWED_CHARS = re.compile(r"[^A-Z0-9<]")
_PLACEHOLDER_ONLY_PATTERN = re.compile(r"^[-_./\\|]+$")


def _clean_mrz(value: str) -> str:
    """Strip characters not allowed in MRZ (keep A-Z, 0-9, <)."""
    return _MRZ_ALLOWED_CHARS.sub("", value.upper())


def normalize_text_value(value: str) -> str | None:
    """Strip whitespace, filter placeholders and null-like values."""
    value = value.strip()
    if value == "" or value.upper() in ("NULL", "N/A"):
        return None
    if _PLACEHOLDER_ONLY_PATTERN.fullmatch(value):
        return None
    return value


def normalize_meta(meta: ImageMeta | None) -> ImageMeta | None:
    """Normalize image metadata values to lowercase."""
    if meta is None:
        return None

    updates: dict[str, Any] = {}
    for field_name in ImageMeta.model_fields:
        value = getattr(meta, field_name)
        if isinstance(value, str):
            normalized = normalize_text_value(value)
            updates[field_name] = normalized.lower() if normalized is not None else None
        else:
            updates[field_name] = value
    return meta.model_copy(update=updates)


def normalize_token_list(value: Any) -> list[str] | None:
    """Parse and clean a token list from string or list input."""
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
        normalized = normalize_text_value(token)
        if normalized is not None:
            tokens.append(normalized)
    return tokens or None


def canonicalize_mrz_line1(value: str | None) -> str | None:
    """Clean and pad MRZ line 1 to 44 characters."""
    if value is None:
        return None
    cleaned = _clean_mrz(value).rstrip("<")
    if cleaned == "":
        return None
    if len(cleaned) <= 5:
        return cleaned.ljust(44, "<")
    return (cleaned[:5] + cleaned[5 : 39 + 5]).ljust(44, "<")


def canonicalize_mrz_line2(value: str | None) -> str | None:
    """Clean and pad MRZ line 2 to 44 characters."""
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


def normalize_fields(data: PassportFields) -> PassportFields:
    """Apply all normalization rules to extracted passport fields."""
    updates: dict[str, Any] = {}
    for field_name in PassportFields.model_fields:
        value = getattr(data, field_name)
        if isinstance(value, str):
            value = normalize_text_value(value)
        updates[field_name] = value

    for date_field in ("DateOfBirth", "DateOfIssue", "DateOfExpiry"):
        val = updates.get(date_field)
        if val is not None and not _DATE_PATTERN.fullmatch(val):
            updates[date_field] = None

    for language in ("Ar", "En"):
        tokens_key = f"GivenNameTokens{language}"
        updates[tokens_key] = normalize_token_list(updates.get(tokens_key))

    updates["MrzLine1"] = canonicalize_mrz_line1(updates.get("MrzLine1"))
    updates["MrzLine2"] = canonicalize_mrz_line2(updates.get("MrzLine2"))
    updates["Sex"] = updates["Sex"] if updates.get("Sex") in {"M", "F"} else None

    return data.model_copy(update=updates)
