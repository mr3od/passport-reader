from __future__ import annotations

import pytest

from passport_core.config import Settings
from passport_core.llm import EXTRACTION_PROMPT, _normalize, build_extractor
from passport_core.models import PassportData


def test_build_extractor_requires_requesty_api_key():
    settings = Settings(_env_file=None, requesty_api_key=None)
    with pytest.raises(ValueError, match="PASSPORT_REQUESTY_API_KEY"):
        build_extractor(settings)


def test_normalize_dates_and_sex():
    data = PassportData(DateOfBirth="1990-01-01", Sex="X", SurnameEn="  DOE ")
    normalized = _normalize(data)

    assert normalized.DateOfBirth is None
    assert normalized.Sex is None
    assert normalized.SurnameEn == "DOE"


def test_extraction_prompt_contains_required_rules():
    assert "Do not invent or infer missing values." in EXTRACTION_PROMPT
    assert "Return strict JSON object only. No markdown. No extra keys." in EXTRACTION_PROMPT
    assert "PassportNumber, CountryCode, MrzLine1, MrzLine2" in EXTRACTION_PROMPT
