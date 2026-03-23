"""Tests for passport_benchmark.compare module."""

from __future__ import annotations

from passport_benchmark.compare import (
    cross_validate,
    evaluate_case,
    fields_match,
    normalize_arabic,
    normalize_english,
    semantic_mrz_match,
)


class TestNormalizeArabic:
    def test_alef_variants(self):
        assert normalize_arabic("أحمد") == normalize_arabic("احمد")
        assert normalize_arabic("إبراهيم") == normalize_arabic("ابراهيم")

    def test_taa_marbuta(self):
        assert normalize_arabic("فاطمة") == normalize_arabic("فاطمه")

    def test_tashkeel_stripped(self):
        assert normalize_arabic("مُحَمَّد") == normalize_arabic("محمد")

    def test_whitespace_collapse(self):
        assert normalize_arabic("عبدالله   مرشد") == normalize_arabic("عبدالله مرشد")

    def test_compound_name_preserved(self):
        # عبدالله should stay as one token
        result = normalize_arabic("عبدالله")
        assert " " not in result


class TestNormalizeEnglish:
    def test_case_insensitive(self):
        assert normalize_english("Socotra") == normalize_english("SOCOTRA")

    def test_hyphen_removed(self):
        assert normalize_english("AL-AKBARI") == normalize_english("AL AKBARI")

    def test_dot_removed(self):
        assert normalize_english("MANG.") == normalize_english("MANG")


class TestFieldsMatch:
    def test_arabic_alef_match(self):
        assert fields_match("SurnameAr", "أحمد", "احمد")

    def test_arabic_taa_marbuta_match(self):
        assert fields_match("SurnameAr", "فاطمة", "فاطمه")

    def test_english_hyphen_match(self):
        assert fields_match("SurnameEn", "AL-AKBARI", "AL AKBARI")

    def test_mrz_trailing_fillers(self):
        assert fields_match(
            "MrzLine1",
            "P<YEMHASAN<<AMAL<SAEED<SAAD<<<<<<<<<<<<<<<<<<",
            "P<YEMHASAN<<AMAL<SAEED<SAAD",
        )

    def test_semantic_mrz_line2_matches_with_extra_fillers(self):
        assert semantic_mrz_match(
            "MrzLine2",
            "09463730<0YEM8411095M2609278<<<<<<<<<<<<<<02",
            "09463730<0YEM8411095M2609278<<<<<<<<<<<<<<<02",
        )

    def test_arabic_token_lists_match(self):
        assert fields_match("GivenNameTokensAr", ["عبدالله", "مرشد"], ["عبدالله", "مرشد"])

    def test_english_token_lists_no_match(self):
        assert not fields_match("GivenNameTokensEn", ["SALEM"], ["MOHAMMED"])


class TestEvaluateCase:
    def test_perfect_match(self):
        expected = {
            "PassportNumber": "12345678",
            "SurnameEn": "AL-TEST",
            "SurnameAr": "الاختبار",
            "Sex": "M",
        }
        actual = {
            "PassportNumber": "12345678",
            "SurnameEn": "AL TEST",  # hyphen difference — should match
            "SurnameAr": "الاختبار",
            "Sex": "M",
        }
        result = evaluate_case("test_001", expected, actual)
        matched = [f for f in result.fields if f.status == "match"]
        assert any(f.field_name == "SurnameEn" for f in matched)

    def test_hallucination(self):
        expected = {"ProfessionAr": None}
        actual = {"ProfessionAr": "طالب"}
        result = evaluate_case("test_002", expected, actual)
        prof = next(f for f in result.fields if f.field_name == "ProfessionAr")
        assert prof.status == "hallucination"

    def test_omission(self):
        expected = {"ProfessionEn": "STUDENT"}
        actual = {"ProfessionEn": None}
        result = evaluate_case("test_003", expected, actual)
        prof = next(f for f in result.fields if f.field_name == "ProfessionEn")
        assert prof.status == "omission"

    def test_misread(self):
        expected = {"SurnameAr": "العكبري"}
        actual = {"SurnameAr": "الاكبري"}
        result = evaluate_case("test_004", expected, actual)
        surname = next(f for f in result.fields if f.field_name == "SurnameAr")
        assert surname.status == "misread"

    def test_accuracy_calculation(self):
        expected = {
            "PassportNumber": "12345678",
            "SurnameEn": "TEST",
            "GivenNameTokensEn": ["JOHN"],
        }
        actual = {
            "PassportNumber": "12345678",
            "SurnameEn": "TEST",
            "GivenNameTokensEn": ["JANE"],  # misread
        }
        result = evaluate_case("test_005", expected, actual)
        # 2 matches, 1 misread out of 3 scorable → 66.7%
        scorable = [f for f in result.fields if f.status != "both_null"]
        matches = [f for f in scorable if f.status == "match"]
        assert len(matches) == 2
        assert len(scorable) == 3

    def test_place_of_birth_ar_uses_semantic_component_scoring(self):
        expected = {
            "PlaceOfBirthAr": "اليمن - حضرموت",
            "BirthCityAr": "حضرموت",
            "BirthCountryAr": "اليمن",
        }
        actual = {
            "PlaceOfBirthAr": "حضرموت اليمن",
            "BirthCityAr": "حضرموت",
            "BirthCountryAr": "اليمن",
        }
        result = evaluate_case("test_006", expected, actual)
        place = next(f for f in result.fields if f.field_name == "PlaceOfBirthAr")
        assert place.status == "match"

    def test_place_of_birth_ar_still_fails_when_city_is_wrong(self):
        expected = {
            "PlaceOfBirthAr": "اليمن - حضرموت",
            "BirthCityAr": "حضرموت",
            "BirthCountryAr": "اليمن",
        }
        actual = {
            "PlaceOfBirthAr": "اليمن - عدن",
            "BirthCityAr": "عدن",
            "BirthCountryAr": "اليمن",
        }
        result = evaluate_case("test_007", expected, actual)
        place = next(f for f in result.fields if f.field_name == "PlaceOfBirthAr")
        assert place.status == "misread"


class TestCrossValidate:
    def test_mrz_name_and_rebuild_match(self):
        actual = {
            "PassportNumber": "14323310",
            "CountryCode": "YEM",
            "MrzLine1": "P<YEMHASAN<<AMAL<SAEED<SAAD<<<<<<<<<<<<<<<<<",
            "MrzLine2": "14323310<5YEM7501012F3012095<<<<<<<<<<<<<<02",
            "SurnameEn": "HASAN",
            "GivenNameTokensEn": ["AMAL", "SAEED", "SAAD"],
            "GivenNameTokensAr": ["أمال", "سعيد", "سعد"],
            "DateOfBirth": "01/01/1975",
            "DateOfExpiry": "09/12/2030",
            "Sex": "F",
        }
        assert cross_validate(actual) == []

    def test_warns_on_mrz_surname_tokens_and_rebuild_mismatch(self):
        actual = {
            "PassportNumber": "14323310",
            "CountryCode": "YEM",
            "MrzLine1": "P<YEMHASAN<<AMAL<SAEED<SAAD<<<<<<<<<<<<<<<<<",
            "MrzLine2": "14323310<5YEM7501012F3012095<<<<<<<<<<<<<<02",
            "SurnameEn": "HASSAN",
            "GivenNameTokensEn": ["AMAL", "SAEED", "SARA"],
            "GivenNameTokensAr": ["أمال", "سعيد", "سارة"],
            "DateOfBirth": "01/01/1975",
            "DateOfExpiry": "09/12/2030",
            "Sex": "F",
        }
        warnings = cross_validate(actual)
        assert any("SurnameEn:" in warning for warning in warnings)
        assert any("GivenNameTokensEn:" in warning for warning in warnings)
        assert any("MrzLine1 rebuild mismatch:" in warning for warning in warnings)

    def test_authority_style_surname_does_not_warn(self):
        actual = {
            "PassportNumber": "15173185",
            "CountryCode": "YEM",
            "MrzLine1": "P<YEMBINSUWAIDAN<<LANA<ABDULLAH<SAEED<<<<<<<",
            "MrzLine2": "15173185<3YEM1202029F3012039<<<<<<<<<<<<<<02",
            "SurnameEn": "BIN SUWAIDAN",
            "GivenNameTokensEn": ["LANA", "ABDULLAH", "SAEED"],
            "GivenNameTokensAr": ["لناء", "عبدالله", "سعيد"],
            "DateOfBirth": "02/02/2012",
            "DateOfExpiry": "03/12/2030",
            "Sex": "F",
        }
        warnings = cross_validate(actual)
        assert not any("SurnameEn:" in warning for warning in warnings)
        assert not any("MrzLine1 rebuild mismatch:" in warning for warning in warnings)

    def test_final_mrz_given_name_truncation_does_not_warn(self):
        actual = {
            "PassportNumber": "09893429",
            "CountryCode": "YEM",
            "MrzLine1": "P<YEMALHAMED<<AHLAM<MOHAMMED<ABDULLAH<HUSSEI",
            "MrzLine2": "09893429<2YEM7910029F2706100<<<<<<<<<<<<<<08",
            "SurnameEn": "AL-HAMED",
            "GivenNameTokensEn": ["AHLAM", "MOHAMMED", "ABDULLAH", "HUSSEIN"],
            "GivenNameTokensAr": ["أحلام", "محمد", "عبدالله", "حسين"],
            "DateOfBirth": "02/10/1979",
            "DateOfExpiry": "10/06/2027",
            "Sex": "F",
        }
        warnings = cross_validate(actual)
        assert not any("SurnameEn:" in warning for warning in warnings)
        assert not any("GivenNameTokensEn:" in warning for warning in warnings)
