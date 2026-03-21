from __future__ import annotations

from pathlib import Path

from passport_core.benchmark import (
    GroundTruthSample,
    SampleRun,
    _extract_usage_tokens,
    field_comparison,
    load_ground_truth,
    normalized_value,
    score_normalized_prediction,
    score_mrz_prediction,
    score_prediction,
    summarize,
)
from passport_core.models import PassportData


def test_load_ground_truth_reads_fixture_rows():
    fixtures = Path(__file__).parent / "fixtures"
    csv_path = fixtures / "ground_truth.csv"

    samples = load_ground_truth(csv_path, fixtures)
    with csv_path.open("r", encoding="utf-8") as handle:
        expected_count = len({line.split(",", 1)[0] for i, line in enumerate(handle) if i > 0})

    assert len(samples) == expected_count
    assert all(isinstance(s, GroundTruthSample) for s in samples)
    assert all(s.image_path.exists() for s in samples)


def test_score_prediction_counts_exact_matches():
    expected = PassportData(PassportNumber="A1", CountryCode="YEM", Sex="M")
    actual = PassportData(PassportNumber="A1", CountryCode="YEM", Sex="F")

    matched, total = score_prediction(expected, actual)

    assert total == len(PassportData.model_fields)
    assert matched == total - 1


def test_normalized_accuracy_ignores_text_punctuation_and_order():
    expected = PassportData(
        PlaceOfBirthAr="اليمن - حضرموت",
        PlaceOfBirthEn="HADRAMOUT - YEM",
        IssuingAuthorityEn="SANAA",
        MrzLine1="P<YEMABC",
    )
    actual = PassportData(
        PlaceOfBirthAr="حضرموت - اليمن",
        PlaceOfBirthEn="HADRAMOUT YEM",
        IssuingAuthorityEn="SANA'A",
        MrzLine1="P<YEMABX",
    )

    normalized_matched, normalized_total = score_normalized_prediction(expected, actual)
    mrz_matched, mrz_total = score_mrz_prediction(expected, actual)
    fields = field_comparison(expected, actual)

    assert normalized_value("PlaceOfBirthAr", expected.PlaceOfBirthAr) == "اليمن حضرموت"
    assert normalized_matched == normalized_total
    assert mrz_matched == 1
    assert mrz_total == 2
    assert fields["PlaceOfBirthAr"]["strict_matched"] is False
    assert fields["PlaceOfBirthAr"]["normalized_matched"] is True
    assert fields["MrzLine1"]["normalized_matched"] is False


def test_load_ground_truth_deduplicates_duplicate_images(tmp_path: Path):
    csv_path = tmp_path / "ground_truth.csv"
    csv_path.write_text(
        "image,PassportNumber\nsample.jpg,1\nsample.jpg,1\n",
        encoding="utf-8",
    )
    (tmp_path / "sample.jpg").write_bytes(b"x")

    samples = load_ground_truth(csv_path, tmp_path)

    assert len(samples) == 1
    assert samples[0].expected.PassportNumber == "1"


def test_load_ground_truth_rejects_conflicting_duplicate_images(tmp_path: Path):
    csv_path = tmp_path / "ground_truth.csv"
    csv_path.write_text(
        "image,PassportNumber\nsample.jpg,1\nsample.jpg,2\n",
        encoding="utf-8",
    )
    (tmp_path / "sample.jpg").write_bytes(b"x")

    try:
        load_ground_truth(csv_path, tmp_path)
    except ValueError as exc:
        assert "Conflicting duplicate image row" in str(exc)
    else:
        raise AssertionError("Expected conflicting duplicate rows to fail")


def test_extract_usage_tokens_accepts_dict_usage_payload():
    result = type("Result", (), {"usage": {"input_tokens": 12, "output_tokens": 34}})()

    assert _extract_usage_tokens(result) == (12, 34)


def test_summarize_with_pricing():
    p1 = PassportData(PassportNumber="A1", CountryCode="YEM", Sex="M")
    p2 = PassportData(PassportNumber="A2", CountryCode="YEM", Sex="F")
    runs = [
        SampleRun("a.jpg", 0.4, 18, 16, 2, 18, 16, 2, 1000, 200, p1, p1),
        SampleRun("b.jpg", 0.6, 17, 15, 2, 18, 16, 2, 1200, 300, p2, p2),
    ]
    pricing = {
        "openai-responses/gpt-5-mini": {
            "input_per_1m": 0.15,
            "output_per_1m": 0.60,
        }
    }

    out = summarize("openai-responses/gpt-5-mini", runs, pricing)

    assert out["strict_accuracy"] == 0.9722
    assert out["normalized_accuracy"] == 0.9688
    assert out["mrz_accuracy"] == 1.0
    assert out["avg_latency_s"] == 0.5
    assert out["input_tokens"] == 2200
    assert out["output_tokens"] == 500
    assert out["estimated_cost_usd"] is not None
    assert len(out["sample_details"]) == 2
    assert out["sample_details"][0]["image"] == "a.jpg"
    assert "fields" in out["sample_details"][0]
