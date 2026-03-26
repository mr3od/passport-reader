from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np

from passport_core.config import Settings
from passport_core.io import LoadedImage
from passport_core.models import (
    BoundingBox,
    FaceCropResult,
    FaceDetectionResult,
    PassportData,
    ValidationResult,
)
from passport_core.workflow import PassportWorkflow, _WorkflowCandidate


def _mock_method(obj: object, attr: str) -> MagicMock:
    """Return a mock-backed attribute from a partially constructed workflow object."""
    return cast(MagicMock, getattr(cast(Any, obj), attr))


def _set_mock_method(obj: object, attr: str, mock: MagicMock) -> MagicMock:
    """Assign a MagicMock to a typed method attribute in tests."""
    setattr(cast(Any, obj), attr, mock)
    return mock


def _mk_workflow() -> PassportWorkflow:
    workflow = object.__new__(PassportWorkflow)
    workflow.settings = Settings()
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
    _mock_method(workflow.validator, "validate").return_value = MagicMock(
        result=ValidationResult(is_passport=True, page_quad=[(0, 0), (1, 0), (1, 1), (0, 1)])
    )
    _mock_method(workflow.face_detector, "detect").return_value = FaceDetectionResult(
        bbox_original=BoundingBox(x=5, y=6, width=20, height=30, score=0.9)
    )
    _mock_method(workflow.face_cropper, "crop").return_value = None

    result = workflow.process_loaded(loaded)

    assert result.validation.is_passport is True
    assert result.face is not None
    assert result.face_crop is None
    assert result.face_crop_bytes is None
    assert result.has_face_crop is False
    assert result.data is None
    assert result.is_complete is False
    _mock_method(workflow.extractor, "extract").assert_not_called()


def test_process_loaded_uses_best_transformed_candidate_before_extraction():
    workflow = _mk_workflow()
    loaded = LoadedImage(
        source="telegram://file-2",
        data=b"raw",
        mime_type="image/jpeg",
        filename="passport.jpg",
        bgr=np.zeros((100, 100, 3), dtype=np.uint8),
    )

    seen_arrays = {"count": 0}

    def validate(image) -> MagicMock:
        if isinstance(image, LoadedImage) and image.source == "telegram://file-2":
            return MagicMock(result=ValidationResult(is_passport=False))
        if not isinstance(image, LoadedImage):
            seen_arrays["count"] += 1
        if seen_arrays["count"] == 1:
            return MagicMock(
                result=ValidationResult(
                    is_passport=True,
                    page_quad=[(0, 0), (10, 0), (10, 10), (0, 10)],
                )
            )
        return MagicMock(result=ValidationResult(is_passport=False))

    def detect(image: LoadedImage, page_quad: list[tuple[int, int]] | None) -> FaceDetectionResult:
        assert page_quad is not None
        return FaceDetectionResult(
            bbox_original=BoundingBox(x=5, y=6, width=20, height=30, score=0.9),
            landmarks_original=[(10, 10), (20, 10), (15, 18), (11, 26), (19, 26)],
        )

    def crop(image, bbox: BoundingBox | None) -> FaceCropResult | None:
        if not isinstance(image, LoadedImage):
            assert bbox is not None
            return FaceCropResult(
                bbox_original=bbox,
                width=20,
                height=30,
                jpeg_bytes=b"face",
            )
        return None

    _set_mock_method(
        workflow,
        "validate_passport",
        MagicMock(side_effect=lambda image: validate(image).result),
    )
    _set_mock_method(workflow, "detect_face", MagicMock(side_effect=detect))
    _set_mock_method(workflow, "crop_face", MagicMock(side_effect=crop))
    _set_mock_method(
        workflow,
        "extract_data",
        MagicMock(return_value=PassportData(PassportNumber="A123")),
    )

    result = workflow.process_loaded(loaded)

    assert result.loaded.source == "telegram://file-2"
    assert result.processed_loaded is not None
    assert result.processed_loaded.source.endswith("#rot180")
    assert result.validation.is_passport is True
    assert result.face_crop is not None
    assert result.data is not None
    assert result.data.PassportNumber == "A123"
    _mock_method(workflow, "extract_data").assert_called_once_with(result.processed_loaded)


def test_prepare_loaded_maps_geometry_back_to_original_coordinates():
    workflow = _mk_workflow()
    loaded = LoadedImage(
        source="telegram://geometry",
        data=b"raw",
        mime_type="image/jpeg",
        filename="passport.jpg",
        bgr=np.zeros((100, 200, 3), dtype=np.uint8),
    )
    bbox = BoundingBox(x=20, y=30, width=40, height=10, score=0.9)
    face = FaceDetectionResult(
        bbox_original=bbox,
        landmarks_original=[(20, 30), (40, 30), (30, 35), (22, 38), (38, 38)],
    )
    crop = FaceCropResult(
        bbox_original=bbox,
        width=40,
        height=10,
        jpeg_bytes=b"face",
    )
    _set_mock_method(
        workflow,
        "_evaluate_candidates",
        MagicMock(
            return_value=[
                _WorkflowCandidate(
                    name="rot90",
                    image_bgr=np.zeros((200, 100, 3), dtype=np.uint8),
                    validation=ValidationResult(
                        is_passport=True,
                        page_quad=[(10, 20), (30, 20), (30, 40), (10, 40)],
                    ),
                    face=face,
                    face_crop=crop,
                )
            ]
        ),
    )

    result = workflow.prepare_loaded(loaded)

    assert result.loaded is loaded
    assert result.processed_loaded is not None
    assert result.processed_loaded.source.endswith("#rot90")
    assert result.validation.page_quad == [(20, 89), (20, 69), (40, 69), (40, 89)]
    assert result.face is not None
    assert result.face.bbox_original == BoundingBox(x=30, y=39, width=10, height=40, score=0.9)
    assert result.face_crop is not None
    assert result.face_crop.bbox_original == BoundingBox(
        x=30,
        y=39,
        width=10,
        height=40,
        score=0.9,
    )


def test_promoted_transformed_candidate_uses_jpeg_mime_and_suffix():
    workflow = _mk_workflow()
    loaded = LoadedImage(
        source="telegram://mime",
        data=b"png-bytes",
        mime_type="image/png",
        filename="passport.png",
        bgr=np.zeros((40, 60, 3), dtype=np.uint8),
    )

    promoted = workflow._make_candidate_loaded(
        loaded,
        name="rot180",
        image_bgr=np.zeros((40, 60, 3), dtype=np.uint8),
    )

    assert promoted.mime_type == "image/jpeg"
    assert promoted.filename.endswith(".jpg")
    assert promoted.source.endswith("#rot180")


def test_process_loaded_returns_incomplete_when_no_candidates():
    workflow = _mk_workflow()
    loaded = LoadedImage(
        source="telegram://empty",
        data=b"raw",
        mime_type="image/jpeg",
        filename="passport.jpg",
        bgr=np.zeros((50, 50, 3), dtype=np.uint8),
    )
    _set_mock_method(workflow, "_evaluate_candidates", MagicMock(return_value=[]))

    result = workflow.process_loaded(loaded)

    assert result.loaded is loaded
    assert result.validation.is_passport is False
    assert result.data is None


def test_prepare_loaded_returns_incomplete_when_no_candidates():
    workflow = _mk_workflow()
    loaded = LoadedImage(
        source="telegram://empty-prepare",
        data=b"raw",
        mime_type="image/jpeg",
        filename="passport.jpg",
        bgr=np.zeros((50, 50, 3), dtype=np.uint8),
    )
    _set_mock_method(workflow, "_evaluate_candidates", MagicMock(return_value=[]))

    result = workflow.prepare_loaded(loaded)

    assert result.loaded is loaded
    assert result.validation.is_passport is False
    assert result.face is None
    assert result.face_crop is None


def test_early_stop_happens_only_after_face_crop_exists():
    workflow = _mk_workflow()
    workflow.settings = Settings(
        candidate_early_stop_validation_score=50.0,
        candidate_early_stop_face_score=0.85,
        candidate_early_stop_landmark_score=0.75,
    )
    loaded = LoadedImage(
        source="telegram://stop",
        data=b"raw",
        mime_type="image/jpeg",
        filename="passport.jpg",
        bgr=np.zeros((50, 60, 3), dtype=np.uint8),
    )

    def validate(image):
        return ValidationResult(
            is_passport=True,
            page_quad=[(0, 0), (10, 0), (10, 10), (0, 10)],
        )

    face = FaceDetectionResult(
        bbox_original=BoundingBox(x=1, y=2, width=20, height=30, score=0.95),
        landmarks_original=[(10, 10), (20, 10), (15, 15), (11, 22), (19, 22)],
    )
    crop_calls = {"count": 0}

    def crop(image, bbox):
        crop_calls["count"] += 1
        if crop_calls["count"] == 1:
            return None
        assert bbox is not None
        return FaceCropResult(bbox_original=bbox, width=20, height=30, jpeg_bytes=b"face")

    _set_mock_method(workflow, "validate_passport", MagicMock(side_effect=validate))
    _set_mock_method(workflow, "detect_face", MagicMock(return_value=face))
    _set_mock_method(workflow, "crop_face", MagicMock(side_effect=crop))

    candidates = workflow._evaluate_candidates(loaded)

    assert len(candidates) >= 2
    assert crop_calls["count"] >= 2


def test_extract_retries_raise_first_exception_from_last():
    workflow = _mk_workflow()
    workflow.settings = Settings(candidate_max_extraction_attempts=2)
    loaded = LoadedImage(
        source="telegram://errors",
        data=b"raw",
        mime_type="image/jpeg",
        filename="passport.jpg",
        bgr=np.zeros((40, 40, 3), dtype=np.uint8),
    )

    bbox = BoundingBox(x=1, y=2, width=20, height=30, score=0.95)
    face = FaceDetectionResult(
        bbox_original=bbox,
        landmarks_original=[(10, 10), (20, 10), (15, 15), (11, 22), (19, 22)],
    )
    crop = FaceCropResult(bbox_original=bbox, width=20, height=30, jpeg_bytes=b"face")
    _set_mock_method(
        workflow,
        "_evaluate_candidates",
        MagicMock(
            return_value=[
                _WorkflowCandidate(
                    name="identity",
                    image_bgr=loaded.bgr,
                    loaded=loaded,
                    validation=ValidationResult(is_passport=True),
                    face=face,
                    face_crop=crop,
                ),
                _WorkflowCandidate(
                    name="rot180",
                    image_bgr=loaded.bgr,
                    validation=ValidationResult(is_passport=True),
                    face=face,
                    face_crop=crop,
                ),
            ]
        ),
    )

    first = RuntimeError("first")
    last = RuntimeError("last")
    _set_mock_method(workflow, "extract_data", MagicMock(side_effect=[first, last]))

    try:
        workflow.process_loaded(loaded)
    except RuntimeError as exc:
        assert exc is first
        assert exc.__cause__ is last
    else:
        raise AssertionError("expected RuntimeError")


def test_process_bytes_uses_loaded_bytes_and_returns_complete_result():
    workflow = _mk_workflow()
    loaded = LoadedImage(
        source="telegram://1",
        data=b"raw",
        mime_type="image/jpeg",
        filename="x.jpg",
        bgr=np.zeros((100, 120, 3), dtype=np.uint8),
    )
    _set_mock_method(workflow, "load_bytes", MagicMock(return_value=loaded))
    _mock_method(workflow.validator, "validate").return_value = MagicMock(
        result=ValidationResult(is_passport=True, page_quad=[(0, 0), (10, 0), (10, 10), (0, 10)])
    )
    _mock_method(workflow.face_detector, "detect").return_value = FaceDetectionResult(
        bbox_original=BoundingBox(x=5, y=6, width=20, height=30, score=0.9)
    )
    _mock_method(workflow.face_cropper, "crop").return_value = FaceCropResult(
        bbox_original=BoundingBox(x=5, y=6, width=20, height=30, score=0.9),
        width=20,
        height=30,
        jpeg_bytes=b"face",
    )
    _mock_method(workflow.extractor, "extract").return_value = PassportData(PassportNumber="A123")

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
