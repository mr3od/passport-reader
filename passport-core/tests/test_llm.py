from __future__ import annotations

import pytest

from passport_core.llm import _normalize, _parse_json_text, _strip_prefix
from passport_core.models import PassportData


def test_strip_prefix():
    assert _strip_prefix("google/gemini-2.0", "google") == "gemini-2.0"
    assert _strip_prefix("gemini-2.0", "google") == "gemini-2.0"


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
