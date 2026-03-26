from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import cv2
import numpy as np
from passport_core.extraction.models import PassportFields

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GROUND_TRUTH_CSV = FIXTURES_DIR / "ground_truth.csv"


def _load_ground_truth() -> list[dict[str, str]]:
    with GROUND_TRUTH_CSV.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _resolve_image_path(image_name: str) -> Path:
    target = FIXTURES_DIR / image_name
    if target.exists():
        return target

    stem = Path(image_name).stem
    for ext in (".jpg", ".jpeg", ".png"):
        candidate = FIXTURES_DIR / f"{stem}{ext}"
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Fixture image not found for {image_name}")


def _image_bytes(path: Path) -> bytes:
    return path.read_bytes()


class _GoldenExtractorStub:
    def __init__(self, expected_by_hash: dict[str, PassportFields]) -> None:
        self._expected_by_hash = expected_by_hash

    def extract(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> PassportFields:
        del mime_type
        key = hashlib.sha256(image_bytes).hexdigest()
        return self._expected_by_hash[key]


def _passport_data_from_row(row: dict[str, str]) -> PassportFields:
    payload = {k: (v if v != "" else None) for k, v in row.items() if k != "image"}
    return PassportFields.model_validate(payload)


def test_golden_fixtures_are_loadable_and_well_formed() -> None:
    rows = _load_ground_truth()
    assert rows, "ground_truth.csv must include at least one sample"

    for row in rows:
        assert row["image"]
        image_path = _resolve_image_path(row["image"])
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        assert image is not None, f"Could not decode fixture: {image_path.name}"
        assert isinstance(image, np.ndarray)

        parsed = _passport_data_from_row(row)
        assert parsed.PassportNumber is not None
        assert parsed.CountryCode == "YEM"


def test_golden_extractor_contract_fields_match_expected() -> None:
    rows = _load_ground_truth()

    expected_by_hash: dict[str, PassportFields] = {}
    for row in rows:
        image_path = _resolve_image_path(row["image"])
        data = _image_bytes(image_path)
        digest = hashlib.sha256(data).hexdigest()
        expected_by_hash[digest] = _passport_data_from_row(row)

    extractor = _GoldenExtractorStub(expected_by_hash)

    for row in rows:
        image_path = _resolve_image_path(row["image"])
        actual = extractor.extract(_image_bytes(image_path))
        expected = _passport_data_from_row(row)
        assert actual.model_dump() == expected.model_dump()
