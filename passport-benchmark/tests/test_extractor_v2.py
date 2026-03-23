from __future__ import annotations

import pytest

from passport_benchmark.extractor_v2 import (
    Confidence,
    ImageMeta,
    PassportFields,
    _apply_confidence_layer,
    _canonicalize_mrz_line1,
    _canonicalize_mrz_line2,
    _normalize,
    _normalize_confidence,
    _normalize_meta,
)


class TestCanonicalizeMrz:
    def test_line1_removes_spacing_and_pads_to_44(self):
        assert _canonicalize_mrz_line1(
            "P<YEMHASAN<<AMAL<SAEED<SAAD"
        ) == "P<YEMHASAN<<AMAL<SAEED<SAAD<<<<<<<<<<<<<<<<<"

    def test_line2_preserves_trailing_check_digits(self):
        assert _canonicalize_mrz_line2(
            "09463730<0YEM8411095M2609278<<<<<<<<<<<<<<<02"
        ) == "09463730<0YEM8411095M2609278<<<<<<<<<<<<<<02"

    def test_line2_cleans_spaces_and_uppercases(self):
        assert _canonicalize_mrz_line2(
            "14323939<2yem6201016m3102097 <<<<<<<<<<<<<<<00"
        ) == "14323939<2YEM6201016M3102097<<<<<<<<<<<<<<00"


class TestNormalize:
    def test_normalize_canonicalizes_mrz_fields(self):
        raw = PassportFields(
            MrzLine1="P<YEMALAKBARI<<SALEM<ABDULLAH<OMAR<<<<<<<<<<<<",
            MrzLine2="09463730<0YEM8411095M2609278<<<<<<<<<<<<<<<02",
        )

        data = _normalize(raw)

        assert data.MrzLine1 == "P<YEMALAKBARI<<SALEM<ABDULLAH<OMAR<<<<<<<<<<"
        assert data.MrzLine2 == "09463730<0YEM8411095M2609278<<<<<<<<<<<<<<02"

    def test_normalize_converts_placeholder_markers_to_null(self):
        raw = PassportFields(
            ProfessionAr="---",
            ProfessionEn=" -- ",
            IssuingAuthorityEn="N/A",
        )

        data = _normalize(raw)

        assert data.ProfessionAr is None
        assert data.ProfessionEn is None
        assert data.IssuingAuthorityEn is None

    def test_normalize_preserves_given_name_token_arrays(self):
        raw = PassportFields(
            GivenNameTokensAr=["أحمد", "خميس", "جمعان", "حسين"],
            GivenNameTokensEn=["AHMED", "KHAMIS", "GUMAAN", "HUSSEIN"],
        )

        data = _normalize(raw)

        assert data.GivenNameTokensAr == ["أحمد", "خميس", "جمعان", "حسين"]
        assert data.GivenNameTokensEn == ["AHMED", "KHAMIS", "GUMAAN", "HUSSEIN"]

    def test_normalize_cleans_empty_tokens(self):
        raw = PassportFields(
            GivenNameTokensAr=["أحمد", " ", "خميس", "---", "جمعان"],
            GivenNameTokensEn=["AHMED", "", "KHAMIS", "N/A", "GUMAAN"],
        )

        data = _normalize(raw)

        assert data.GivenNameTokensAr == ["أحمد", "خميس", "جمعان"]
        assert data.GivenNameTokensEn == ["AHMED", "KHAMIS", "GUMAAN"]

    def test_normalize_meta_lowercases_and_preserves_flags(self):
        meta = ImageMeta(
            orientation="ROTATED_90",
            image_type="PHOTOGRAPHED",
            layout="SINGLE_PAGE",
            image_quality="GOOD",
            mirrored=True,
            skew_level="MILD",
            reasoning="Mirrored photo",
        )

        normalized = _normalize_meta(meta)

        assert normalized is not None
        assert normalized.orientation == "rotated_90"
        assert normalized.image_type == "photographed"
        assert normalized.layout == "single_page"
        assert normalized.image_quality == "good"
        assert normalized.mirrored is True
        assert normalized.skew_level == "mild"

    def test_normalize_confidence_clamps_and_filters_fields(self):
        confidence = Confidence(
            overall=1.2,
            fields={
                "PassportNumber": 0.9,
                "GivenNameTokensAr": -0.5,
                "NotAField": 0.8,
            },
        )

        normalized = _normalize_confidence(confidence)

        assert normalized is not None
        assert normalized.overall == 1.0
        assert normalized.fields == {
            "PassportNumber": 0.9,
            "GivenNameTokensAr": 0.0,
        }

    def test_confidence_layer_caps_mirrored_image(self):
        confidence = Confidence(
            overall=0.98,
            fields={
                "PassportNumber": 0.99,
                "SurnameAr": 0.95,
                "GivenNameTokensAr": 0.95,
            },
        )

        adjusted = _apply_confidence_layer(
            confidence,
            ImageMeta(mirrored=True, image_quality="good", orientation="normal"),
            [],
        )

        assert adjusted is not None
        assert adjusted.overall == pytest.approx(0.35)
        assert adjusted.fields["PassportNumber"] == 0.35
        assert adjusted.fields["SurnameAr"] == 0.35

    def test_confidence_layer_caps_mrz_fields_on_validation_warnings(self):
        confidence = Confidence(
            overall=1.0,
            fields={
                "PassportNumber": 1.0,
                "MrzLine2": 1.0,
                "DateOfBirth": 0.95,
                "SurnameAr": 0.9,
            },
        )

        adjusted = _apply_confidence_layer(
            confidence,
            None,
            [
                "Check digit failures: passport_number, overall",
                "PassportNumber: MRZ='123' vs VIZ='456'",
            ],
        )

        assert adjusted is not None
        assert adjusted.overall is not None
        assert adjusted.overall <= 0.45
        assert adjusted.fields["PassportNumber"] == 0.2
        assert adjusted.fields["MrzLine2"] == 0.2
        assert adjusted.fields["DateOfBirth"] == 0.3
        assert adjusted.fields["SurnameAr"] == 0.9
