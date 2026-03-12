from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from passport_core.io import LoadedImage
from passport_core.models import (
    BoundingBox,
    FaceCropResult,
    FaceDetectionResult,
    PassportData,
    ValidationResult,
)
from passport_core.workflow import PassportWorkflow


def _mk_workflow() -> PassportWorkflow:
    workflow = object.__new__(PassportWorkflow)
    workflow.loader = MagicMock()
    workflow.validator = MagicMock()
    workflow.face_detector = MagicMock()
    workflow.face_cropper = MagicMock()
    workflow.extractor = MagicMock()
    return workflow


def test_process_loaded_requires_face_crop_before_extraction():
    workflow = _mk_workflow()
    loaded = LoadedImage(
        source="telegram://file-1",
        data=b"raw",
        mime_type="image/jpeg",
        filename="passport.jpg",
        bgr=np.zeros((100, 100, 3), dtype=np.uint8),
    )
    workflow.validator.validate.return_value = MagicMock(
        result=ValidationResult(is_passport=True, page_quad=[(0, 0), (1, 0), (1, 1), (0, 1)])
    )
    workflow.face_detector.detect.return_value = FaceDetectionResult(
        bbox_original=BoundingBox(x=5, y=6, width=20, height=30, score=0.9)
    )
    workflow.face_cropper.crop.return_value = None

    result = workflow.process_loaded(loaded)

    assert result.validation.is_passport is True
    assert result.face is not None
    assert result.face_crop is None
    assert result.face_crop_bytes is None
    assert result.has_face_crop is False
    assert result.data is None
    assert result.is_complete is False
    workflow.extractor.extract.assert_not_called()


def test_process_bytes_uses_loaded_bytes_and_returns_complete_result():
    workflow = _mk_workflow()
    loaded = LoadedImage(
        source="telegram://1",
        data=b"raw",
        mime_type="image/jpeg",
        filename="x.jpg",
        bgr=np.zeros((100, 120, 3), dtype=np.uint8),
    )
    workflow.load_bytes = MagicMock(return_value=loaded)
    workflow.validator.validate.return_value = MagicMock(
        result=ValidationResult(is_passport=True, page_quad=[(0, 0), (10, 0), (10, 10), (0, 10)])
    )
    workflow.face_detector.detect.return_value = FaceDetectionResult(
        bbox_original=BoundingBox(x=5, y=6, width=20, height=30, score=0.9)
    )
    workflow.face_cropper.crop.return_value = FaceCropResult(
        bbox_original=BoundingBox(x=5, y=6, width=20, height=30, score=0.9),
        width=20,
        height=30,
        jpeg_bytes=b"face",
    )
    workflow.extractor.extract.return_value = PassportData(PassportNumber="A123")

    result = workflow.process_bytes(b"raw", filename="x.jpg", source="telegram://1")

    assert result.loaded.source == "telegram://1"
    assert result.source == "telegram://1"
    assert result.filename == "x.jpg"
    assert result.mime_type == "image/jpeg"
    assert result.image_bytes == b"raw"
    assert result.face_crop is not None
    assert result.face_crop_bytes == b"face"
    assert result.has_face_crop is True
    assert result.data is not None
    assert result.data.PassportNumber == "A123"
    assert result.is_complete is True
