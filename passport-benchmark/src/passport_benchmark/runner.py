"""Run the passport extractor benchmark.

Usage::

    benchmark-run cases/                           # Score latest run or legacy actual.json
    benchmark-run cases/ --extract                 # Run extractor first, then score
    benchmark-run cases/ --extract --run-id test   # Extract into runs/test/
    benchmark-run cases/ --run-id test             # Score runs/test/

Only cases in ``cases/labeled/`` with an ``expected.json`` are scored.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from passport_benchmark.compare import cross_validate, evaluate_case
from passport_benchmark.report import generate_report

_RUN_ID_SANITIZE = re.compile(r"[^A-Za-z0-9._-]+")


def _find_labeled_cases(cases_dir: Path) -> list[Path]:
    """Return sorted list of case directories under ``cases_dir/labeled/``."""
    labeled = cases_dir / "labeled"
    if not labeled.exists():
        return []
    return sorted(d for d in labeled.iterdir() if d.is_dir() and (d / "expected.json").exists())


def _resolve(root: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return (root / value).resolve()


def _load_core_settings():
    from passport_core.config import Settings

    repo_root = Path(__file__).resolve().parents[3]
    core_root_dir = repo_root / "passport-core"
    core_env_file = core_root_dir / ".env"

    env_file = core_env_file if core_env_file.exists() else None
    settings = cast(Any, Settings)(**({"_env_file": env_file} if env_file else {}))
    settings.assets_dir = _resolve(core_root_dir, settings.assets_dir)
    settings.template_path = _resolve(core_root_dir, settings.template_path)
    settings.face_model_path = _resolve(core_root_dir, settings.face_model_path)

    if settings.requesty_api_key is None:
        raise RuntimeError(
            "Missing PASSPORT_REQUESTY_API_KEY. "
            f"Expected it in {core_env_file} or the current environment."
        )

    return settings


def _benchmark_root(cases_dir: Path) -> Path:
    return cases_dir.parent


def _runs_dir(cases_dir: Path) -> Path:
    return _benchmark_root(cases_dir) / "runs"


def _sanitize_run_id(value: str) -> str:
    sanitized = _RUN_ID_SANITIZE.sub("-", value.strip()).strip("-.")
    return sanitized or "run"


def _auto_run_id(model: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{_sanitize_run_id(model)}"


def _latest_run_dir(cases_dir: Path) -> Path | None:
    runs_dir = _runs_dir(cases_dir)
    if not runs_dir.exists():
        return None
    candidates = [d for d in runs_dir.iterdir() if d.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)


def _resolve_run_dir(
    cases_dir: Path,
    run_id: str | None,
    *,
    extract: bool,
    model: str,
) -> tuple[Path | None, str | None]:
    if run_id:
        sanitized = _sanitize_run_id(run_id)
        return _runs_dir(cases_dir) / sanitized, sanitized
    if extract:
        generated = _auto_run_id(model)
        return _runs_dir(cases_dir) / generated, generated

    latest = _latest_run_dir(cases_dir)
    if latest is not None:
        return latest, latest.name
    return None, None


def _case_run_dir(run_dir: Path, case_id: str) -> Path:
    return run_dir / "cases" / case_id


def _git_metadata(repo_root: Path) -> dict[str, Any]:
    def _capture(*args: str) -> str | None:
        try:
            return subprocess.check_output(
                ["git", *args],
                cwd=repo_root,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None

    commit = _capture("rev-parse", "HEAD")
    branch = _capture("branch", "--show-current")
    status = _capture("status", "--short")
    return {
        "git_commit": commit,
        "git_branch": branch,
        "git_dirty": bool(status),
    }


def _write_run_metadata(run_dir: Path, metadata: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
    )


def _load_run_metadata(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _build_run_metadata(
    *,
    cases_dir: Path,
    run_id: str,
    model: str,
    base_url: str | None,
    extract: bool,
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    metadata = {
        "run_id": run_id,
        "cases_dir": str(cases_dir.resolve()),
        "model": model,
        "base_url": base_url,
        "mode": "extract" if extract else "score",
        "created_at": datetime.now(UTC).isoformat(),
    }
    metadata.update(_git_metadata(repo_root))
    return metadata


def _load_actual_payload(case_dir: Path, run_dir: Path | None) -> dict[str, Any] | None:
    if run_dir is None:
        legacy_path = case_dir / "actual.json"
        if not legacy_path.exists():
            return None
        return json.loads(legacy_path.read_text())

    run_case_dir = _case_run_dir(run_dir, case_dir.name)
    actual_path = run_case_dir / "actual.json"
    if not actual_path.exists():
        return None

    actual = json.loads(actual_path.read_text())
    usage_path = run_case_dir / "usage.json"
    if usage_path.exists():
        actual["_usage"] = json.loads(usage_path.read_text())
    return actual


def run_benchmark(
    cases_dir: Path,
    *,
    extract: bool = False,
    run_id: str | None = None,
    model_override: str | None = None,
) -> None:
    """Evaluate all labeled cases and generate reports."""
    case_dirs = _find_labeled_cases(cases_dir)
    if not case_dirs:
        print(f"No labeled cases found in {cases_dir / 'labeled'}/")
        print("Move case directories with completed expected.json into cases/labeled/")
        sys.exit(1)

    settings = _load_core_settings() if extract else None
    model_name = model_override or (settings.llm_model if settings else "unknown-model")
    run_dir, resolved_run_id = _resolve_run_dir(
        cases_dir,
        run_id,
        extract=extract,
        model=model_name,
    )

    if extract and run_dir is None:
        raise RuntimeError("Failed to determine run directory for extraction.")

    if not extract and run_dir is None:
        print("No benchmark runs found under runs/ and no legacy actual.json files detected.")
        print("Use --extract to create a run or provide --run-id to score a specific run.")
        sys.exit(1)

    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        print(f"Run ID: {resolved_run_id}")
        print(f"Run directory: {run_dir}")
        if extract:
            metadata = _build_run_metadata(
                cases_dir=cases_dir,
                run_id=resolved_run_id or run_dir.name,
                model=model_name,
                base_url=settings.requesty_base_url if settings else None,
                extract=True,
            )
            _write_run_metadata(run_dir, metadata)
        else:
            metadata = _load_run_metadata(run_dir)
    else:
        metadata = {}

    print(f"Evaluating {len(case_dirs)} labeled cases...\n")

    results = []

    for case_dir in case_dirs:
        case_id = case_dir.name
        expected = json.loads((case_dir / "expected.json").read_text())
        image_path = case_dir / "input.jpeg"

        if extract and image_path.exists():
            from passport_benchmark.extractor_v2 import PassportExtractorV2

            if settings is None or settings.requesty_api_key is None:
                raise RuntimeError("Extractor settings were not loaded correctly.")
            extractor = PassportExtractorV2(
                api_key=settings.requesty_api_key.get_secret_value(),
                model=model_name,
                base_url=settings.requesty_base_url,
            )
            extraction = extractor.extract(image_path.read_bytes())
            actual = extraction.data.model_dump()
            actual["_meta"] = extraction.meta.model_dump() if extraction.meta else None
            actual["_reasoning"] = (
                extraction.reasoning.model_dump() if extraction.reasoning else None
            )  # noqa: E501
            actual["_confidence"] = (
                extraction.confidence.model_dump() if extraction.confidence else None
            )
            actual["warnings"] = extraction.warnings
            actual["_usage"] = extraction.usage
            if run_dir is None:
                raise RuntimeError("Missing run directory while writing extracted results.")
            run_case_dir = _case_run_dir(run_dir, case_id)
            run_case_dir.mkdir(parents=True, exist_ok=True)
            (run_case_dir / "actual.json").write_text(
                json.dumps(actual, indent=2, ensure_ascii=False) + "\n"
            )
            (run_case_dir / "usage.json").write_text(
                json.dumps(extraction.usage, indent=2, ensure_ascii=False) + "\n"
            )
            if extraction.message_history_json is not None:
                (run_case_dir / "messages.json").write_text(
                    extraction.message_history_json + "\n"
                )
            print(f"  EXTRACTED {case_id}")
        else:
            actual = _load_actual_payload(case_dir, run_dir)
            if actual is None:
                location = (
                    f"{_case_run_dir(run_dir, case_id) / 'actual.json'}"
                    if run_dir is not None
                    else f"{case_dir / 'actual.json'}"
                )
                print(f"  SKIP {case_id} — no actual.json at {location}")
                continue

        result = evaluate_case(case_id, expected, actual)
        usage_data = actual.get("_usage")
        if isinstance(usage_data, dict):
            result.meta["usage"] = usage_data
        confidence_data = actual.get("_confidence")
        if isinstance(confidence_data, dict):
            result.meta["confidence"] = confidence_data
        if metadata:
            result.meta["run_id"] = metadata.get("run_id", resolved_run_id)
            result.meta["model"] = metadata.get("model", model_name)

        # Also run programmatic cross-validation on actual output
        xval_warnings = cross_validate(actual)
        result.warnings.extend(xval_warnings)

        # Save diff
        diff = {
            fr.field_name: {
                "expected": fr.expected,
                "actual": fr.actual,
                "status": fr.status,
                "group": fr.field_group,
            }
            for fr in result.fields
            if fr.status != "both_null"
        }
        diff_path = (
            _case_run_dir(run_dir, case_id) / "diff.json"
            if run_dir is not None
            else case_dir / "diff.json"
        )
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text(json.dumps(diff, indent=2, ensure_ascii=False) + "\n")

        ec = result.error_counts()
        print(
            f"  {case_id}: {result.accuracy:.0%}  "
            f"({ec['misread']}m {ec['omission']}o {ec['hallucination']}h)"
        )
        results.append(result)

    if results:
        output_dir = run_dir if run_dir is not None else _benchmark_root(cases_dir)
        generate_report(output_dir, results, run_metadata=metadata or None)
        avg = sum(r.accuracy for r in results) / len(results)
        print(f"\n{'=' * 50}")
        print(f"OVERALL: {avg:.1%} average accuracy across {len(results)} cases")
    else:
        print("\nNo cases evaluated.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases_dir", help="Path to benchmark cases directory.")
    parser.add_argument("--extract", action="store_true", help="Run extraction before scoring.")
    parser.add_argument("--run-id", help="Store or read results under runs/<run_id>/")
    parser.add_argument("--model", help="Override the configured model name for extraction.")
    args = parser.parse_args()

    run_benchmark(
        Path(args.cases_dir),
        extract=args.extract,
        run_id=args.run_id,
        model_override=args.model,
    )


if __name__ == "__main__":
    main()
