from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from passport_core.errors import ErrorCode
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

    assert result.trace_id
    assert result.validation.is_passport is True
    assert result.data is not None
    assert result.data.PassportNumber == "A123"
    assert result.error_details == []
    svc.result_store.save.assert_called_once()


def test_process_source_alignment_missing_records_error_code():
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
    assert result.error_details
    assert result.error_details[0].code == ErrorCode.ALIGNMENT_ERROR


def test_process_source_exception_captured_with_code():
    svc = _mk_service()
    svc.loader.load.side_effect = RuntimeError("boom")

    result = svc.process_source("/tmp/a.jpg")

    assert result.validation.is_passport is False
    assert result.error_details
    assert result.error_details[0].code == ErrorCode.INPUT_LOAD_ERROR
    assert "boom" in result.error_details[0].message
