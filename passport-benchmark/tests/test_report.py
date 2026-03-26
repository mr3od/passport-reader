from __future__ import annotations

import csv
from pathlib import Path

from passport_benchmark.compare import CaseResult, FieldResult
from passport_benchmark.report import _bias_summary, generate_report


class TestBiasSummary:
    def test_misread_only_bias(self):
        assert _bias_summary(0, 0, 19) == (
            "**Bias: misread-only.** No hallucinations or omissions were observed."
        )

    def test_misread_dominant_bias(self):
        assert _bias_summary(0, 1, 22) == (
            "**Bias: misread-dominant.** "
            "Most errors are wrong reads, not hallucinations or omissions."
        )

    def test_no_errors_bias(self):
        assert _bias_summary(0, 0, 0) == "**Bias: no errors observed.**"


class TestGenerateReport:
    def test_report_includes_run_metadata_and_usage(self, tmp_path: Path):
        result = CaseResult(
            case_id="case_001",
            meta={
                "layout": "single_page",
                "image_quality": "good",
                "run_id": "run-1",
                "model": "openai-responses/gpt-5-mini",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "requests": 1,
                    "tool_calls": 0,
                },
                "confidence": {
                    "overall": 0.9,
                    "fields": {
                        "PassportNumber": 0.95,
                        "MrzLine1": 0.8,
                        "MrzLine2": 0.7,
                    },
                },
            },
            fields=[
                FieldResult("PassportNumber", "identifiers", "123", "123", "match"),
                FieldResult(
                    "MrzLine1",
                    "mrz",
                    "P<YEMTEST<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
                    "P<YEMWRONG<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
                    "misread",
                ),
                FieldResult(
                    "MrzLine2",
                    "mrz",
                    "12345678<0YEM9001011M3001019<<<<<<<<<<<<<<00",
                    "12345678<0YEM9001011M3001019<<<<<<<<<<<<<<00",
                    "match",
                ),
            ],
            mrz_valid=True,
        )

        generate_report(
            tmp_path,
            [result],
            run_metadata={"run_id": "run-1", "model": "openai-responses/gpt-5-mini"},
        )

        report_text = (tmp_path / "benchmark_report.md").read_text()
        assert "**Run ID:** run-1" in report_text
        assert "**Token usage:** input=10, output=5, total=15, requests=1" in report_text
        assert "**Average confidence on correct fields:** 0.82" in report_text
        assert "**Average confidence on wrong fields:** 0.80" in report_text
        assert "| 0.80 | case_001 | MrzLine1 | misread |" in report_text

        with (tmp_path / "benchmark_results.csv").open() as f:
            rows = list(csv.DictReader(f))

        assert rows[0]["run_id"] == "run-1"
        assert rows[0]["model"] == "openai-responses/gpt-5-mini"
        assert rows[0]["input_tokens"] == "10"
        assert rows[0]["total_tokens"] == "15"

    def test_group_accuracy_ignores_both_null_groups(self, tmp_path: Path):
        result = CaseResult(
            case_id="case_001",
            meta={"layout": "single_page", "image_quality": "good"},
            fields=[
                FieldResult("PassportNumber", "identifiers", "123", "123", "match"),
                FieldResult("ProfessionAr", "profession", None, None, "both_null"),
                FieldResult("ProfessionEn", "profession", None, None, "both_null"),
            ],
            mrz_valid=True,
        )

        generate_report(tmp_path, [result])

        report_text = (tmp_path / "benchmark_report.md").read_text()
        assert "| profession | n/a | ProfessionAr, ProfessionEn |" in report_text
