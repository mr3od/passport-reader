from __future__ import annotations

from pathlib import Path

from passport_core.benchmark import (
    GroundTruthSample,
    SampleRun,
    load_ground_truth,
    score_prediction,
    summarize,
)
from passport_core.models import PassportData


def test_load_ground_truth_reads_fixture_rows():
    fixtures = Path(__file__).parent / "fixtures"
    csv_path = fixtures / "ground_truth.csv"

    samples = load_ground_truth(csv_path, fixtures)

    assert len(samples) == 5
    assert all(isinstance(s, GroundTruthSample) for s in samples)
    assert all(s.image_path.exists() for s in samples)


def test_score_prediction_counts_exact_matches():
    expected = PassportData(PassportNumber="A1", CountryCode="YEM", Sex="M")
    actual = PassportData(PassportNumber="A1", CountryCode="YEM", Sex="F")

    matched, total = score_prediction(expected, actual)

    assert total == len(PassportData.model_fields)
    assert matched == total - 1


def test_summarize_with_pricing():
    runs = [
        SampleRun("a.jpg", 0.4, 18, 18, 1000, 200),
        SampleRun("b.jpg", 0.6, 17, 18, 1200, 300),
    ]
    pricing = {
        "openai-responses/gpt-5-mini": {
            "input_per_1m": 0.15,
            "output_per_1m": 0.60,
        }
    }

    out = summarize("openai-responses/gpt-5-mini", runs, pricing)

    assert out["field_accuracy"] == 0.9722
    assert out["avg_latency_s"] == 0.5
    assert out["input_tokens"] == 2200
    assert out["output_tokens"] == 500
    assert out["estimated_cost_usd"] is not None
