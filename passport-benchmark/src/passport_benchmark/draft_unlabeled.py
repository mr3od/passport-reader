"""Extract draft data for unlabeled benchmark cases.

Usage::

    benchmark-draft-unlabeled cases/ --limit 5

Runs the passport-core extractor on unlabeled cases and writes draft artifacts
next to each case without modifying the blank human-maintained ``expected.json``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from passport_core.extraction import PassportExtractor

from passport_benchmark.runner import _load_core_settings


def _find_unlabeled_cases(cases_dir: Path) -> list[Path]:
    unlabeled = cases_dir / "unlabeled"
    if not unlabeled.exists():
        return []
    return sorted(d for d in unlabeled.iterdir() if d.is_dir() and (d / "input.jpeg").exists())


def _draft_payload(extraction, original_filename: str) -> dict[str, Any]:
    payload = extraction.data.model_dump()
    meta = extraction.meta.model_dump() if extraction.meta else {}
    meta["original_filename"] = original_filename
    payload["_meta"] = meta
    payload["_reasoning"] = extraction.reasoning.model_dump() if extraction.reasoning else None
    payload["_confidence"] = extraction.confidence.model_dump() if extraction.confidence else None
    payload["warnings"] = extraction.warnings
    payload["_usage"] = extraction.usage
    return payload


def draft_unlabeled_cases(
    cases_dir: Path,
    *,
    limit: int | None = None,
    model_override: str | None = None,
    force: bool = False,
) -> int:
    case_dirs = _find_unlabeled_cases(cases_dir)
    if limit is not None:
        case_dirs = case_dirs[:limit]
    if not case_dirs:
        print(f"No unlabeled cases found in {cases_dir / 'unlabeled'}/")
        return 0

    settings = _load_core_settings()
    model_name = model_override or settings.llm_model
    extractor = PassportExtractor(
        api_key=settings.requesty_api_key.get_secret_value(),
        model=model_name,
        base_url=settings.requesty_base_url,
    )

    print(f"Drafting {len(case_dirs)} unlabeled cases with model: {model_name}\n")
    drafted = 0
    skipped = 0

    for case_dir in case_dirs:
        draft_path = case_dir / "draft.json"
        if draft_path.exists() and not force:
            skipped += 1
            print(f"  SKIP {case_dir.name} — draft.json already exists")
            continue

        image_path = case_dir / "input.jpeg"
        extraction = extractor.extract(image_path.read_bytes())
        payload = _draft_payload(extraction, image_path.name)

        draft_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        (case_dir / "draft.usage.json").write_text(
            json.dumps(extraction.usage, indent=2, ensure_ascii=False) + "\n"
        )
        if extraction.message_history_json is not None:
            (case_dir / "draft.messages.json").write_text(extraction.message_history_json + "\n")

        drafted += 1
        print(f"  DRAFTED {case_dir.name}")

    print(f"\nDrafted {drafted} cases")
    print(f"Skipped {skipped} cases")
    return drafted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run extractor_v2 on unlabeled cases and save draft outputs.",
    )
    parser.add_argument("cases_dir", type=Path, help="Path to benchmark cases/ directory")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of unlabeled cases to draft",
    )
    parser.add_argument(
        "--model",
        dest="model_override",
        default=None,
        help="Override the configured model name",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing draft artifacts",
    )
    args = parser.parse_args()

    draft_unlabeled_cases(
        args.cases_dir,
        limit=args.limit,
        model_override=args.model_override,
        force=args.force,
    )


if __name__ == "__main__":
    main()
