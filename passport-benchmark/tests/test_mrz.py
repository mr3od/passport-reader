"""Tests for passport_benchmark.mrz module."""

from __future__ import annotations

import pytest

from passport_benchmark.mrz import (
    build_mrz_line1,
    build_mrz_line2,
    check_digit,
    parse_mrz,
    validate_mrz,
)

# ── Correct 44-char MRZ lines for inline tests ──────────────────

CASE_001_L1 = "P<YEMHASAN<<AMAL<SAEED<SAAD" + "<" * 17
CASE_001_L2 = "14323310<5YEM7501012F3012095<<<<<<<<<<<<<<02"
CASE_005_L1 = "P<YEMALAKBARI<<SALEM<ABDULLAH<OMAR" + "<" * 10
CASE_005_L2 = "09463730<0YEM8411095M2609278<<<<<<<<<<<<<<02"

assert len(CASE_001_L1) == 44
assert len(CASE_001_L2) == 44
assert len(CASE_005_L1) == 44
assert len(CASE_005_L2) == 44


class TestCheckDigit:
    def test_all_zeros(self):
        assert check_digit("000000000") == 0

    def test_known_passport_number(self):
        assert check_digit("14323310<") == 5

    def test_known_dob(self):
        assert check_digit("750101") == 2

    def test_known_expiry(self):
        assert check_digit("290511") == 0


class TestParseMrz:
    def test_case_001_full(self):
        """AMAL SAEED SAAD / HASAN — case_001."""
        parsed = parse_mrz(CASE_001_L1, CASE_001_L2)

        assert parsed.valid
        assert parsed.passport_number == "14323310"
        assert parsed.country_code == "YEM"
        assert parsed.dob == "01/01/1975"
        assert parsed.sex == "F"
        assert parsed.expiry == "09/12/2030"
        assert parsed.surname == "HASAN"
        assert parsed.given_names == "AMAL SAEED SAAD"
        assert all(c.ok for c in parsed.checks)

    def test_case_005_al_akbari(self):
        """SALEM ABDULLAH OMAR / AL-AKBARI — MRZ drops the hyphen."""
        parsed = parse_mrz(CASE_005_L1, CASE_005_L2)

        assert parsed.valid
        assert parsed.surname == "ALAKBARI"
        assert parsed.given_names == "SALEM ABDULLAH OMAR"

    def test_missing_lines(self):
        parsed = parse_mrz(None, None)
        assert not parsed.valid
        assert "missing" in parsed.warnings[0].lower()

    def test_short_line2(self):
        l1 = "P<YEMTEST<<TEST" + "<" * 29
        parsed = parse_mrz(l1, "12345")
        assert not parsed.valid

    def test_invalid_optional_data_digit_fails_parse(self):
        corrupted = "14323310<5YEM7501012F3012095<<<<<<<<<<<<<<92"
        parsed = parse_mrz(CASE_001_L1, corrupted)
        assert not parsed.valid
        assert any(check.name == "optional_data" and not check.ok for check in parsed.checks)

    def test_invalid_overall_digit_fails_parse(self):
        corrupted = "14323310<5YEM7501012F3012095<<<<<<<<<<<<<<03"
        parsed = parse_mrz(CASE_001_L1, corrupted)
        assert not parsed.valid
        assert any(check.name == "overall" and not check.ok for check in parsed.checks)

    def test_all_12_cases_pass(self, benchmark_cases):
        """All ground truth MRZ lines must pass check digit validation."""
        for case_id, data in benchmark_cases.items():
            line1 = data.get("MrzLine1")
            line2 = data.get("MrzLine2")
            if line1 and line2:
                assert len(line1) == 44, f"{case_id} L1 is {len(line1)}"
                assert len(line2) == 44, f"{case_id} L2 is {len(line2)}"
                parsed = parse_mrz(line1, line2)
                assert parsed.valid, f"{case_id}: {parsed.warnings}"


class TestBuildMrz:
    def test_build_line1_case_001(self):
        built = build_mrz_line1("YEM", "HASAN", ["AMAL", "SAEED", "SAAD"])
        assert built == CASE_001_L1

    def test_build_line2_case_001(self):
        built = build_mrz_line2("14323310", "YEM", "01/01/1975", "F", "09/12/2030")
        assert built == CASE_001_L2

    def test_build_line1_removes_non_alphanumeric_inside_name_parts(self):
        built = build_mrz_line1("YEM", "AL AK-BARI", ["ABD", "AL-LAH"])
        assert built == "P<YEMALAKBARI<<ABD<ALLAH<<<<<<<<<<<<<<<<<<<<"


class TestValidateMrz:
    def test_valid(self):
        ok, warnings = validate_mrz(CASE_001_L2)
        assert ok
        assert not warnings

    def test_corrupted_check_digit(self):
        corrupted = "14323310<9YEM7501012F3012095<<<<<<<<<<<<<<02"
        assert len(corrupted) == 44
        ok, warnings = validate_mrz(corrupted)
        assert not ok
        assert any("passport_number" in w for w in warnings)

    def test_corrupted_optional_data_digit(self):
        corrupted = "14323310<5YEM7501012F3012095<<<<<<<<<<<<<<92"
        assert len(corrupted) == 44
        ok, warnings = validate_mrz(corrupted)
        assert not ok
        assert any("optional_data" in w for w in warnings)

    def test_corrupted_overall_digit(self):
        corrupted = "14323310<5YEM7501012F3012095<<<<<<<<<<<<<<03"
        assert len(corrupted) == 44
        ok, warnings = validate_mrz(corrupted)
        assert not ok
        assert any("overall" in w for w in warnings)


@pytest.fixture()
def benchmark_cases():
    """Load all expected.json from cases/labeled/."""
    import json
    from pathlib import Path

    cases_dir = Path(__file__).parent.parent / "cases" / "labeled"
    result = {}
    if cases_dir.exists():
        for case_dir in sorted(cases_dir.iterdir()):
            expected = case_dir / "expected.json"
            if expected.exists():
                result[case_dir.name] = json.loads(expected.read_text())
    return result
