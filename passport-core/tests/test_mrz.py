from __future__ import annotations

from passport_core.mrz import parse_mrz, validate_mrz

CASE_001_L1 = "P<YEMHASAN<<AMAL<SAEED<SAAD" + "<" * 17
CASE_001_L2 = "14323310<5YEM7501012F3012095<<<<<<<<<<<<<<02"


def test_validate_mrz_accepts_valid_td3_line2() -> None:
    ok, warnings = validate_mrz(CASE_001_L2)

    assert ok is True
    assert warnings == []


def test_validate_mrz_rejects_missing_required_check_digits() -> None:
    corrupted = list(CASE_001_L2)
    for index in (9, 19, 27, 43):
        corrupted[index] = "<"

    ok, warnings = validate_mrz("".join(corrupted))

    assert ok is False
    assert "MRZ line 2 passport_number check digit missing or invalid" in warnings
    assert "MRZ line 2 dob check digit missing or invalid" in warnings
    assert "MRZ line 2 expiry check digit missing or invalid" in warnings
    assert "MRZ line 2 overall check digit missing or invalid" in warnings


def test_parse_mrz_marks_missing_required_check_digits_invalid() -> None:
    corrupted = list(CASE_001_L2)
    for index in (9, 19, 27, 43):
        corrupted[index] = "<"

    parsed = parse_mrz(CASE_001_L1, "".join(corrupted))

    assert parsed.valid is False
    assert "MRZ line 2 passport_number check digit missing or invalid" in parsed.warnings
    assert "MRZ line 2 overall check digit missing or invalid" in parsed.warnings


def test_validate_mrz_rejects_non_44_character_line2() -> None:
    ok, warnings = validate_mrz(CASE_001_L2 + "X")

    assert ok is False
    assert warnings == ["MRZ line 2 length is 45, expected 44"]
