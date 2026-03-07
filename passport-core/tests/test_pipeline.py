from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from passport_core.models import PassportData, ValidationResult
from passport_core.pipeline import PassportCoreService


def _mk_service() -> PassportCoreService:
    svc = object.__new__(PassportCoreService)
    svc.loader = MagicMock()
    svc.binary_store = MagicMock()
    svc.result_store = MagicMock()
    svc.csv_exporter = MagicMock()
    svc.validator = MagicMock()
    svc.face_detector = MagicMock()
    svc.extractor = MagicMock()
    return svc


def test_process_source_happy_path():
    svc = _mk_service()
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    svc.loader.load.return_value = SimpleNamespace(
        data=b"raw",
        filename="x.jpg",
        mime_type="image/jpeg",
        bgr=image,
    )
    svc.binary_store.save.side_effect = ["orig://1", "aligned://1"]
    svc.validator.validate.return_value = SimpleNamespace(
        result=ValidationResult(is_passport=True),
        aligned_bgr=image,
        homography_template_to_work=None,
        work_to_original_scale=1.0,
    )
    svc.face_detector.detect.return_value = None
    svc.extractor.extract.return_value = PassportData(PassportNumber="A123")

    result = svc.process_source("/tmp/a.jpg")

    assert result.validation.is_passport is True
    assert result.data is not None
    assert result.data.PassportNumber == "A123"
    assert result.errors == []
    svc.result_store.save.assert_called_once()


def test_process_source_alignment_missing_records_error():
    svc = _mk_service()
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    svc.loader.load.return_value = SimpleNamespace(
        data=b"raw",
        filename="x.jpg",
        mime_type="image/jpeg",
        bgr=image,
    )
    svc.binary_store.save.return_value = "orig://1"
    svc.validator.validate.return_value = SimpleNamespace(
        result=ValidationResult(is_passport=True),
        aligned_bgr=None,
        homography_template_to_work=None,
        work_to_original_scale=1.0,
    )

    result = svc.process_source("/tmp/a.jpg")

    assert result.validation.is_passport is True
    assert result.data is None
    assert any("alignment failed" in err.lower() for err in result.errors)


def test_process_source_exception_captured():
    svc = _mk_service()
    svc.loader.load.side_effect = RuntimeError("boom")

    result = svc.process_source("/tmp/a.jpg")

    assert result.validation.is_passport is False
    assert "boom" in result.errors[0]
