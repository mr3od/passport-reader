from __future__ import annotations

from passport_core.llm import _normalize
from passport_core.models import PassportData


def test_normalize_returns_copied_model_with_cleaned_values():
    original = PassportData(
        PassportNumber=" 123456 ",
        DateOfBirth="NULL",
        DateOfIssue="2023-01-01",
        DateOfExpiry="01/01/2030",
        Sex=" x ",
        GivenNamesEn="  AHMED  ",
    )

    normalized = _normalize(original)

    assert normalized is not original
    assert normalized.PassportNumber == "123456"
    assert normalized.DateOfBirth is None
    assert normalized.DateOfIssue is None
    assert normalized.DateOfExpiry == "01/01/2030"
    assert normalized.Sex is None
    assert normalized.GivenNamesEn == "AHMED"
    assert original.PassportNumber == " 123456 "
    assert original.DateOfBirth == "NULL"
    assert original.DateOfIssue == "2023-01-01"
    assert original.Sex == " x "


def test_normalize_keeps_valid_sex_values():
    assert _normalize(PassportData(Sex="M")).Sex == "M"
    assert _normalize(PassportData(Sex="F")).Sex == "F"
    assert _normalize(PassportData(Sex="")).Sex is None
