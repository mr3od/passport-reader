from __future__ import annotations

import pytest

from passport_core.config import Settings
from passport_core.llm import (
    EXTRACTION_PROMPT,
    _normalize,
    _parse_json_text,
    _resolve_requesty_api_key,
)
from passport_core.models import PassportData


def test_resolve_requesty_api_key_prefers_requesty_key():
    settings = Settings(
        _env_file=None,
        requesty_api_key="requesty-k",
        openai_api_key="openai-k",
    )
    assert _resolve_requesty_api_key(settings) == "requesty-k"


def test_resolve_requesty_api_key_falls_back_openai_key():
    settings = Settings(
        _env_file=None,
        requesty_api_key=None,
        openai_api_key="openai-k",
    )
    assert _resolve_requesty_api_key(settings) == "openai-k"


def test_resolve_requesty_api_key_fails_when_missing():
    settings = Settings(
        _env_file=None,
        requesty_api_key=None,
        openai_api_key=None,
        google_api_key=None,
    )
    with pytest.raises(ValueError, match="PASSPORT_REQUESTY_API_KEY"):
        _resolve_requesty_api_key(settings)


def test_normalize_dates_and_sex():
    data = PassportData(DateOfBirth="1990-01-01", Sex="X", SurnameEn="  DOE ")
    normalized = _normalize(data)

    assert normalized.DateOfBirth is None
    assert normalized.Sex is None
    assert normalized.SurnameEn == "DOE"


def test_parse_json_text_invalid():
    with pytest.raises(ValueError, match="valid JSON"):
        _parse_json_text("not-json")


def test_parse_json_text_valid():
    payload = '{"PassportNumber":"A123","CountryCode":null}'
    parsed = _parse_json_text(payload)
    assert parsed.PassportNumber == "A123"


def test_extraction_prompt_contains_required_rules():
    assert "Do not invent or infer missing values." in EXTRACTION_PROMPT
    assert "Return strict JSON object only. No markdown. No extra keys." in EXTRACTION_PROMPT
    assert "PassportNumber, CountryCode, MrzLine1, MrzLine2" in EXTRACTION_PROMPT
