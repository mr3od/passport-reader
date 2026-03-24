"""Organize raw passport images into benchmark case directories.

Usage::

    benchmark-organize agency-input/ cases/

Images go into ``cases/unlabeled/case_NNN/input.jpeg`` with a blank
``expected.json`` skeleton.  Once you fill in ground truth and verify it,
move the case directory to ``cases/labeled/`` and update ``manifest.csv``.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

_PASSPORT_DATA_SKELETON: dict[str, None] = {
    "PassportNumber": None,
    "CountryCode": None,
    "MrzLine1": None,
    "MrzLine2": None,
    "SurnameAr": None,
    "GivenNameTokensAr": None,
    "SurnameEn": None,
    "GivenNameTokensEn": None,
    "DateOfBirth": None,
    "PlaceOfBirthAr": None,
    "PlaceOfBirthEn": None,
    "BirthCityAr": None,
    "BirthCityEn": None,
    "BirthCountryAr": None,
    "BirthCountryEn": None,
    "Sex": None,
    "DateOfIssue": None,
    "DateOfExpiry": None,
    "ProfessionAr": None,
    "ProfessionEn": None,
    "IssuingAuthorityAr": None,
    "IssuingAuthorityEn": None,
}

_META_SKELETON: dict[str, object] = {
    "is_passport": True,
    "orientation": "normal",
    "image_type": None,
    "layout": None,
    "image_quality": None,
    "original_filename": None,
    "reasoning": None,
}


def _collect_images(input_dir: Path) -> list[Path]:
    return sorted(
        (p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda p: p.name.lower(),
    )


def _next_case_number(cases_dir: Path) -> int:
    """Find the highest existing case number across labeled/ and unlabeled/."""
    highest = 0
    for sub in ("labeled", "unlabeled"):
        d = cases_dir / sub
        if not d.exists():
            continue
        for entry in d.iterdir():
            if entry.is_dir() and entry.name.startswith("case_"):
                try:
                    num = int(entry.name.split("_")[1])
                    highest = max(highest, num)
                except (IndexError, ValueError):
                    pass
    return highest + 1


def organize(input_dir: Path, cases_dir: Path) -> None:
    """Copy images from *input_dir* into ``cases_dir/unlabeled/case_NNN/``."""
    unlabeled = cases_dir / "unlabeled"
    unlabeled.mkdir(parents=True, exist_ok=True)
    (cases_dir / "labeled").mkdir(parents=True, exist_ok=True)

    images = _collect_images(input_dir)
    if not images:
        print(f"No images found in {input_dir}")
        sys.exit(1)

    start = _next_case_number(cases_dir)
    manifest_path = cases_dir.parent / "manifest.csv"

    # Load existing manifest rows
    existing_rows: list[dict[str, str]] = []
    existing_originals: set[str] = set()
    if manifest_path.exists():
        with manifest_path.open(newline="") as f:
            reader = csv.DictReader(f)
            existing_rows = list(reader)
            existing_originals = {r["original_filename"] for r in existing_rows}

    new_rows: list[dict[str, str]] = []
    added = 0

    for img_path in images:
        if img_path.name in existing_originals:
            continue  # Skip already-organized images

        case_id = f"case_{start + added:03d}"
        case_dir = unlabeled / case_id
        case_dir.mkdir(exist_ok=True)

        shutil.copy2(img_path, case_dir / "input.jpeg")

        # Write skeleton expected.json
        skeleton: dict[str, Any] = {
            "_meta": {**_META_SKELETON, "original_filename": img_path.name},
            **_PASSPORT_DATA_SKELETON,
        }
        (case_dir / "expected.json").write_text(
            json.dumps(skeleton, indent=2, ensure_ascii=False) + "\n"
        )

        new_rows.append(
            {
                "case_id": case_id,
                "original_filename": img_path.name,
                "partition": "unlabeled",
                "layout": "",
                "image_type": "",
                "image_quality": "",
                "ground_truth_status": "pending",
                "notes": "",
            }
        )
        added += 1
        print(f"  {case_id} ← {img_path.name}")

    # Write manifest (append new rows)
    all_rows = existing_rows + new_rows
    fieldnames = [
        "case_id",
        "original_filename",
        "partition",
        "layout",
        "image_type",
        "image_quality",
        "ground_truth_status",
        "notes",
    ]
    with manifest_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nAdded {added} new cases to {unlabeled}/")
    print(f"Skipped {len(images) - added} already-organized images")
    print(f"Manifest: {manifest_path}")


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input_dir> <cases_dir>")
        print(f"Example: {sys.argv[0]} agency-input cases")
        sys.exit(1)
    organize(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()
