from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from passport_core.llm import EXTRACTION_PROMPT, _normalize
from passport_core.models import PassportData


@dataclass(slots=True)
class GroundTruthSample:
    image_name: str
    image_path: Path
    expected: PassportData


@dataclass(slots=True)
class SampleRun:
    image_name: str
    latency_s: float
    strict_matched_fields: int
    normalized_matched_fields: int
    mrz_matched_fields: int
    total_fields: int
    enjaz_total_fields: int
    mrz_total_fields: int
    input_tokens: int | None
    output_tokens: int | None
    expected: PassportData
    actual: PassportData


MRZ_FIELDS = {"MrzLine1", "MrzLine2"}
ENJAZ_TEXT_FIELDS = {
    "SurnameAr",
    "GivenNamesAr",
    "SurnameEn",
    "GivenNamesEn",
    "PlaceOfBirthAr",
    "PlaceOfBirthEn",
    "ProfessionAr",
    "ProfessionEn",
    "IssuingAuthorityAr",
    "IssuingAuthorityEn",
}


def _normalize_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value)


def _resolve_image_path(fixtures_dir: Path, image_name: str) -> Path:
    candidate = fixtures_dir / image_name
    if candidate.exists():
        return candidate

    stem = Path(image_name).stem
    for ext in (".jpg", ".jpeg", ".png"):
        alt = fixtures_dir / f"{stem}{ext}"
        if alt.exists():
            return alt

    raise FileNotFoundError(f"Fixture image not found for {image_name}")


def load_ground_truth(csv_path: Path, fixtures_dir: Path) -> list[GroundTruthSample]:
    rows: list[GroundTruthSample] = []
    seen_images: set[str] = set()
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            image_name = row["image"]
            if image_name in seen_images:
                continue
            seen_images.add(image_name)

            image_path = _resolve_image_path(fixtures_dir, image_name)
            payload = {k: (_normalize_value(v)) for k, v in row.items() if k != "image"}
            expected = PassportData.model_validate(payload)
            rows.append(
                GroundTruthSample(
                    image_name=image_name,
                    image_path=image_path,
                    expected=expected,
                )
            )
    return rows


def score_prediction(expected: PassportData, actual: PassportData) -> tuple[int, int]:
    matched = 0
    total = 0
    for field_name in PassportData.model_fields:
        total += 1
        ev = _normalize_value(getattr(expected, field_name))
        av = _normalize_value(getattr(actual, field_name))
        if ev == av:
            matched += 1
    return matched, total


def normalized_value(field_name: str, value: Any) -> str | None:
    raw = _normalize_value(value)
    if raw is None:
        return None
    if field_name in MRZ_FIELDS:
        return raw
    if field_name not in ENJAZ_TEXT_FIELDS:
        return raw.upper()

    text = re.sub(r"[^\w\s]", "", raw.upper(), flags=re.UNICODE)
    tokens = [token for token in text.split() if token]
    return " ".join(sorted(tokens)) if tokens else None


def score_enjaz_prediction(expected: PassportData, actual: PassportData) -> tuple[int, int]:
    matched = 0
    total = 0
    for field_name in PassportData.model_fields:
        if field_name in MRZ_FIELDS:
            continue
        total += 1
        ev = normalized_value(field_name, getattr(expected, field_name))
        av = normalized_value(field_name, getattr(actual, field_name))
        if ev == av:
            matched += 1
    return matched, total


def score_mrz_prediction(expected: PassportData, actual: PassportData) -> tuple[int, int]:
    matched = 0
    total = 0
    for field_name in MRZ_FIELDS:
        total += 1
        ev = _normalize_value(getattr(expected, field_name))
        av = _normalize_value(getattr(actual, field_name))
        if ev == av:
            matched += 1
    return matched, total


def field_comparison(
    expected: PassportData,
    actual: PassportData,
) -> dict[str, dict[str, str | None | bool]]:
    out: dict[str, dict[str, str | None | bool]] = {}
    for field_name in PassportData.model_fields:
        ev = _normalize_value(getattr(expected, field_name))
        av = _normalize_value(getattr(actual, field_name))
        out[field_name] = {
            "expected": ev,
            "actual": av,
            "strict_matched": ev == av,
            "normalized_expected": normalized_value(field_name, getattr(expected, field_name)),
            "normalized_actual": normalized_value(field_name, getattr(actual, field_name)),
            "normalized_matched": normalized_value(
                field_name,
                getattr(expected, field_name),
            )
            == normalized_value(field_name, getattr(actual, field_name)),
        }
    return out


def _usage_tokens(usage: Any, key: str) -> int | None:
    value = getattr(usage, key, None)
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        inner = value.get(key)
        return inner if isinstance(inner, int) else None
    return None


def _extract_usage_tokens(result: Any) -> tuple[int | None, int | None]:
    usage_obj = None
    usage_callable = getattr(result, "usage", None)
    if callable(usage_callable):
        usage_obj = usage_callable()
    elif usage_callable is not None:
        usage_obj = usage_callable

    if usage_obj is None:
        return None, None

    input_tokens = _usage_tokens(usage_obj, "input_tokens")
    output_tokens = _usage_tokens(usage_obj, "output_tokens")
    if input_tokens is None:
        input_tokens = _usage_tokens(usage_obj, "request_tokens")
    return input_tokens, output_tokens


def benchmark_model(
    *,
    model: str,
    base_url: str,
    api_key: str,
    samples: list[GroundTruthSample],
) -> list[SampleRun]:
    from pydantic_ai import Agent, BinaryContent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    agent = Agent(
        model=OpenAIChatModel(model, provider=OpenAIProvider(base_url=base_url, api_key=api_key)),
        instructions=EXTRACTION_PROMPT,
        output_type=PassportData,
        retries=1,
    )

    runs: list[SampleRun] = []
    for sample in samples:
        image_bytes = sample.image_path.read_bytes()
        mime_type = "image/jpeg"
        if sample.image_path.suffix.lower() == ".png":
            mime_type = "image/png"

        start = time.perf_counter()
        result = agent.run_sync(
            [
                "Extract passport fields from this image.",
                BinaryContent(data=image_bytes, media_type=mime_type),
            ]
        )
        latency = time.perf_counter() - start

        output = result.output
        if not isinstance(output, PassportData):
            raise ValueError(f"{model} returned non-PassportData output for {sample.image_name}")

        actual = _normalize(output)
        strict_matched, total = score_prediction(sample.expected, actual)
        normalized_matched, enjaz_total = score_enjaz_prediction(sample.expected, actual)
        mrz_matched, mrz_total = score_mrz_prediction(sample.expected, actual)
        input_tokens, output_tokens = _extract_usage_tokens(result)

        runs.append(
            SampleRun(
                image_name=sample.image_name,
                latency_s=latency,
                strict_matched_fields=strict_matched,
                normalized_matched_fields=normalized_matched,
                mrz_matched_fields=mrz_matched,
                total_fields=total,
                enjaz_total_fields=enjaz_total,
                mrz_total_fields=mrz_total,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                expected=sample.expected,
                actual=actual,
            )
        )

    return runs


def summarize(
    model: str,
    runs: list[SampleRun],
    pricing: dict[str, dict[str, float]] | None,
) -> dict[str, Any]:
    total_matched = sum(r.strict_matched_fields for r in runs)
    total_fields = sum(r.total_fields for r in runs)
    strict_accuracy = (total_matched / total_fields) if total_fields else 0.0
    normalized_matched = sum(r.normalized_matched_fields for r in runs)
    enjaz_total_fields = sum(r.enjaz_total_fields for r in runs)
    normalized_accuracy = (
        normalized_matched / enjaz_total_fields if enjaz_total_fields else 0.0
    )
    mrz_matched = sum(r.mrz_matched_fields for r in runs)
    mrz_total_fields = sum(r.mrz_total_fields for r in runs)
    mrz_accuracy = mrz_matched / mrz_total_fields if mrz_total_fields else 0.0

    latencies = [r.latency_s for r in runs]
    avg_latency = statistics.fmean(latencies) if latencies else 0.0
    p95_latency = sorted(latencies)[int(0.95 * (len(latencies) - 1))] if latencies else 0.0

    input_tokens = sum(r.input_tokens or 0 for r in runs)
    output_tokens = sum(r.output_tokens or 0 for r in runs)
    usage_available = any(r.input_tokens is not None or r.output_tokens is not None for r in runs)

    estimated_cost = None
    if pricing and model in pricing and usage_available:
        inp = pricing[model].get("input_per_1m", 0.0)
        out = pricing[model].get("output_per_1m", 0.0)
        estimated_cost = (input_tokens / 1_000_000) * inp + (output_tokens / 1_000_000) * out

    return {
        "model": model,
        "samples": len(runs),
        "strict_accuracy": round(strict_accuracy, 4),
        "normalized_accuracy": round(normalized_accuracy, 4),
        "mrz_accuracy": round(mrz_accuracy, 4),
        "avg_latency_s": round(avg_latency, 4),
        "p95_latency_s": round(p95_latency, 4),
        "input_tokens": input_tokens if usage_available else None,
        "output_tokens": output_tokens if usage_available else None,
        "estimated_cost_usd": round(estimated_cost, 6) if estimated_cost is not None else None,
        "sample_details": [
            {
                "image": r.image_name,
                "latency_s": round(r.latency_s, 4),
                "strict_matched_fields": r.strict_matched_fields,
                "normalized_matched_fields": r.normalized_matched_fields,
                "mrz_matched_fields": r.mrz_matched_fields,
                "total_fields": r.total_fields,
                "enjaz_total_fields": r.enjaz_total_fields,
                "mrz_total_fields": r.mrz_total_fields,
                "strict_accuracy": round(
                    (r.strict_matched_fields / r.total_fields) if r.total_fields else 0.0,
                    4,
                ),
                "normalized_accuracy": round(
                    (
                        r.normalized_matched_fields / r.enjaz_total_fields
                        if r.enjaz_total_fields
                        else 0.0
                    ),
                    4,
                ),
                "mrz_accuracy": round(
                    (r.mrz_matched_fields / r.mrz_total_fields) if r.mrz_total_fields else 0.0,
                    4,
                ),
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "fields": field_comparison(r.expected, r.actual),
            }
            for r in runs
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark models on passport ground truth fixtures"
    )
    parser.add_argument(
        "--models",
        required=True,
        help=(
            "Comma-separated model ids, "
            "e.g. openai-responses/gpt-5-mini,google/gemini-3.1-flash-lite-preview"
        ),
    )
    parser.add_argument("--api-key", required=True, help="Requesty API key")
    parser.add_argument("--base-url", default="https://router.requesty.ai/v1")
    parser.add_argument(
        "--ground-truth-csv",
        default="tests/fixtures/ground_truth.csv",
    )
    parser.add_argument("--fixtures-dir", default="tests/fixtures")
    parser.add_argument(
        "--pricing-json",
        default="",
        help='Optional JSON file: {"model": {"input_per_1m": 0.15, "output_per_1m": 0.6}}',
    )
    parser.add_argument("--out-json", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    csv_path = Path(args.ground_truth_csv)
    fixtures_dir = Path(args.fixtures_dir)
    samples = load_ground_truth(csv_path, fixtures_dir)

    pricing = None
    if args.pricing_json:
        pricing = json.loads(Path(args.pricing_json).read_text(encoding="utf-8"))

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    all_summaries: list[dict[str, Any]] = []

    for model in models:
        runs = benchmark_model(
            model=model,
            base_url=args.base_url,
            api_key=args.api_key,
            samples=samples,
        )
        summary = summarize(model, runs, pricing)
        all_summaries.append(summary)

        print(
            f"{model}: strict={summary['strict_accuracy']:.4f} "
            f"normalized={summary['normalized_accuracy']:.4f} "
            f"mrz={summary['mrz_accuracy']:.4f} "
            f"avg={summary['avg_latency_s']:.3f}s "
            f"p95={summary['p95_latency_s']:.3f}s "
            f"tokens(in/out)={summary['input_tokens']}/{summary['output_tokens']} "
            f"cost=${summary['estimated_cost_usd']}"
        )

    ranked = sorted(
        all_summaries,
        key=lambda x: (x["normalized_accuracy"], x["strict_accuracy"], -x["avg_latency_s"]),
        reverse=True,
    )

    print("\nRanking (best first):")
    for idx, row in enumerate(ranked, start=1):
        print(
            f"{idx}. {row['model']} normalized={row['normalized_accuracy']:.4f} "
            f"strict={row['strict_accuracy']:.4f} mrz={row['mrz_accuracy']:.4f} "
            f"avg={row['avg_latency_s']:.3f}s cost={row['estimated_cost_usd']}"
        )

    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps({"results": all_summaries, "ranking": ranked}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
