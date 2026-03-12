from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from passport_core.errors import ErrorCode
from passport_core.io import LoadedImage
from passport_core.models import (
    BoundingBox,
    FaceCropResult,
    FaceDetectionResult,
    PassportData,
    ValidationResult,
)
from passport_core.pipeline import PassportCoreService


def _mk_service() -> PassportCoreService:
    svc = object.__new__(PassportCoreService)
    svc.workflow = MagicMock()
    svc.binary_store = MagicMock()
    svc.result_store = MagicMock()
    svc.csv_exporter = MagicMock()
    return svc


def test_process_source_happy_path():
    svc = _mk_service()
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    loaded = LoadedImage(
        source="/tmp/a.jpg",
        data=b"raw",
        filename="x.jpg",
        mime_type="image/jpeg",
        bgr=image,
    )
    svc.workflow.load_source.return_value = loaded
    svc.binary_store.save.return_value = "orig://1"
    svc.workflow.crop_face.return_value = FaceCropResult(
        bbox_original=BoundingBox(x=30, y=40, width=50, height=60, score=0.9),
        width=50,
        height=60,
        jpeg_bytes=b"jpeg",
    )
    svc.binary_store.save.side_effect = ["orig://1", "faces://1"]
    svc.workflow.validate_passport.return_value = ValidationResult(
        is_passport=True,
        page_quad=[(10, 20), (110, 20), (110, 120), (10, 120)],
    )
    svc.workflow.detect_face.return_value = FaceDetectionResult(
        bbox_original=BoundingBox(x=30, y=40, width=50, height=60, score=0.9),
    )
    svc.workflow.extract_data.return_value = PassportData(PassportNumber="A123")

    result = svc.process_source("/tmp/a.jpg")

    assert result.trace_id
    assert result.validation.is_passport is True
    assert result.data is not None
    assert result.data.PassportNumber == "A123"
    assert result.passport_image_uri == "orig://1"
    assert result.face_crop_uri == "faces://1"
    assert result.error_details == []
    svc.result_store.save.assert_called_once()
    svc.workflow.detect_face.assert_called_once_with(
        loaded,
        [(10, 20), (110, 20), (110, 120), (10, 120)],
    )
    svc.workflow.crop_face.assert_called_once_with(
        loaded,
        svc.workflow.detect_face.return_value.bbox_original,
    )
    svc.workflow.extract_data.assert_called_once_with(loaded)


def test_process_source_not_passport_skips_extraction():
    svc = _mk_service()
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    svc.workflow.load_source.return_value = LoadedImage(
        source="/tmp/a.jpg",
        data=b"raw",
        filename="x.jpg",
        mime_type="image/jpeg",
        bgr=image,
    )
    svc.binary_store.save.return_value = "orig://1"
    svc.workflow.validate_passport.return_value = ValidationResult(is_passport=False)

    result = svc.process_source("/tmp/a.jpg")

    assert result.validation.is_passport is False
    assert result.data is None
    assert result.passport_image_uri == "orig://1"
    assert result.face_crop_uri is None
    svc.workflow.extract_data.assert_not_called()


def test_process_source_exception_captured_with_code():
    svc = _mk_service()
    svc.workflow.load_source.side_effect = RuntimeError("boom")

    result = svc.process_source("/tmp/a.jpg")

    assert result.validation.is_passport is False
    assert result.error_details
    assert result.error_details[0].code == ErrorCode.INPUT_LOAD_ERROR
    assert "boom" in result.error_details[0].message


def test_process_source_skips_extraction_when_face_crop_missing():
    svc = _mk_service()
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    loaded = LoadedImage(
        source="/tmp/a.jpg",
        data=b"raw",
        filename="x.jpg",
        mime_type="image/jpeg",
        bgr=image,
    )
    svc.workflow.load_source.return_value = loaded
    svc.binary_store.save.return_value = "orig://1"
    svc.workflow.validate_passport.return_value = ValidationResult(
        is_passport=True,
        page_quad=[(10, 20), (110, 20), (110, 120), (10, 120)],
    )
    svc.workflow.detect_face.return_value = FaceDetectionResult(
        bbox_original=BoundingBox(x=30, y=40, width=50, height=60, score=0.9),
    )
    svc.workflow.crop_face.return_value = None

    result = svc.process_source("/tmp/a.jpg")

    assert result.data is None
    assert result.face_crop_uri is None
    assert result.error_details
    assert result.error_details[0].code == ErrorCode.FACE_DETECTION_ERROR
    svc.workflow.extract_data.assert_not_called()


def test_crop_face_returns_cropped_face_for_valid_passport():
    svc = _mk_service()
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    loaded = LoadedImage(
        source="/tmp/a.jpg",
        data=b"raw",
        filename="a.jpg",
        mime_type="image/jpeg",
        bgr=image,
    )
    svc.workflow.load_source.return_value = loaded
    svc.workflow.validate_passport.return_value = ValidationResult(
        is_passport=True,
        page_quad=[(10, 20), (110, 20), (110, 120), (10, 120)],
    )
    svc.workflow.detect_face.return_value = FaceDetectionResult(
        bbox_original=BoundingBox(x=30, y=40, width=50, height=60, score=0.9),
    )
    svc.workflow.crop_face.return_value = FaceCropResult(
        bbox_original=BoundingBox(x=30, y=40, width=50, height=60, score=0.9),
        width=50,
        height=60,
        jpeg_bytes=b"jpeg",
    )
    svc.binary_store.save.return_value = "faces://1"

    result = svc.crop_face("/tmp/a.jpg")

    assert result is not None
    assert result.width == 50
    assert result.stored_uri == "faces://1"
    svc.workflow.detect_face.assert_called_once_with(
        loaded,
        [(10, 20), (110, 20), (110, 120), (10, 120)],
    )
    svc.workflow.crop_face.assert_called_once()
    svc.binary_store.save.assert_called_once_with(
        b"jpeg",
        folder="faces",
        filename="a_face.jpg",
        content_type="image/jpeg",
    )


def test_crop_face_returns_none_when_not_passport():
    svc = _mk_service()
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    svc.workflow.load_source.return_value = LoadedImage(
        source="/tmp/a.jpg",
        data=b"raw",
        filename="a.jpg",
        mime_type="image/jpeg",
        bgr=image,
    )
    svc.workflow.validate_passport.return_value = ValidationResult(is_passport=False)

    result = svc.crop_face("/tmp/a.jpg")

    assert result is None
    svc.workflow.detect_face.assert_not_called()
    svc.workflow.crop_face.assert_not_called()
