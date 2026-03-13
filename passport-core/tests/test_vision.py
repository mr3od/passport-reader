from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from passport_core.config import Settings
from passport_core.models import BoundingBox
from passport_core.vision import (
    PassportFaceCropper,
    PassportFaceDetector,
    PassportFeatureValidator,
    RetinaFacePriorConfig,
)


def test_validator_accepts_same_image(reference_template_path, sample_bgr_image):
    settings = Settings(
        template_path=reference_template_path,
        validator_min_good_matches=5,
        validator_min_inliers=4,
        validator_min_inlier_ratio=0.2,
    )
    validator = PassportFeatureValidator(settings)
    match = validator.validate(sample_bgr_image)

    assert match.result.is_passport is True
    assert match.homography_image_to_template is not None
    assert len(match.result.page_quad or []) == 4


def test_validator_rejects_blank(reference_template_path):
    settings = Settings(template_path=reference_template_path)
    validator = PassportFeatureValidator(settings)

    blank = np.zeros((400, 600, 3), dtype=np.uint8)
    match = validator.validate(blank)

    assert match.result.is_passport is False


def test_validator_rejects_negative_determinant(
    reference_template_path,
    sample_bgr_image,
    monkeypatch,
):
    settings = Settings(
        template_path=reference_template_path,
        validator_min_good_matches=5,
        validator_min_inliers=4,
        validator_min_inlier_ratio=0.2,
    )
    validator = PassportFeatureValidator(settings)

    original_find_homography = __import__("cv2").findHomography

    def fake_find_homography(src, dst, method, threshold):
        homography, mask = original_find_homography(src, dst, method, threshold)
        assert homography is not None
        reflected = homography.copy()
        reflected[0, 0] *= -1.0
        return reflected, mask

    monkeypatch.setattr("passport_core.vision.cv2.findHomography", fake_find_homography)

    match = validator.validate(sample_bgr_image)

    assert match.result.is_passport is False


def test_projected_quad_uses_source_image_area(reference_template_path):
    settings = Settings(
        template_path=reference_template_path,
        validator_min_quad_area_ratio=0.20,
        validator_max_quad_area_ratio=0.50,
    )
    validator = PassportFeatureValidator(settings)
    projected = np.asarray([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.float32)

    assert validator._is_valid_projected_quad(projected, (200, 200, 3)) is True
    assert validator._is_valid_projected_quad(projected, (1000, 1000, 3)) is False


def test_face_detector_maps_bbox_from_cropped_page_quad():
    detector = object.__new__(PassportFaceDetector)
    detector.settings = Settings(face_score_threshold=0.60, face_nms_threshold=0.40)
    detector.model_width = 100
    detector.model_height = 100

    class StubInput:
        def __init__(self) -> None:
            self.name = "input"
            self.shape = [1, 3, 100, 100]

    class StubSession:
        def __init__(self) -> None:
            self.calls = []

        def run(self, _output_names, feed_dict):
            self.calls.append(feed_dict["input"].shape)
            prior_count = len(detector._priors)
            loc = np.zeros((1, prior_count, 4), dtype=np.float32)
            conf = np.zeros((1, prior_count, 2), dtype=np.float32)
            landms = np.zeros((1, prior_count, 10), dtype=np.float32)
            loc[0, 0] = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32)
            conf[0, 0, 1] = 0.9
            return [loc, conf, landms]

        def get_inputs(self):
            return [StubInput()]

    detector.prior_config = RetinaFacePriorConfig(
        min_sizes=((20,),),
        steps=(100,),
        variance=(0.1, 0.2),
    )
    detector._priors = PassportFaceDetector._prior_boxes(detector)
    detector.session = StubSession()
    detector.input_name = "input"
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    face = detector.detect(image, [(50, 40), (150, 40), (150, 140), (50, 140)])

    assert detector.session.calls == [(1, 3, 100, 100)]
    assert face.bbox_original is not None
    assert face.bbox_original.x == 90
    assert face.bbox_original.y == 80
    assert face.bbox_original.width == 20
    assert face.bbox_original.height == 20


def test_face_cropper_crops_and_clips_bbox():
    cropper = PassportFaceCropper()
    image = np.zeros((100, 120, 3), dtype=np.uint8)
    image[15:60, 10:70] = 255

    result = cropper.crop(
        image,
        BoundingBox(x=10, y=15, width=80, height=90, score=0.9),
    )

    assert result is not None
    assert result.width == 80
    assert result.height == 85
    assert result.bbox_original.x == 10
    assert result.bbox_original.y == 15
    assert result.jpeg_bytes


def test_landmark_decode_vectorized_matches_expected_formula():
    detector = object.__new__(PassportFaceDetector)
    detector.prior_config = RetinaFacePriorConfig(variance=(0.1, 0.2))
    priors = np.asarray([[0.5, 0.6, 0.2, 0.4]], dtype=np.float32)
    landms = np.asarray([[0.1, 0.2, 0.0, 0.1, -0.1, 0.0, 0.2, -0.2, -0.2, 0.3]], dtype=np.float32)

    decoded = detector._decode_landmarks(landms, priors)

    expected = np.asarray(
        [[0.502, 0.608, 0.5, 0.604, 0.498, 0.6, 0.504, 0.592, 0.496, 0.612]],
        dtype=np.float32,
    )
    np.testing.assert_allclose(decoded, expected)


def test_decode_uses_cached_priors():
    detector = object.__new__(PassportFaceDetector)
    detector.settings = Settings(face_score_threshold=0.60, face_nms_threshold=0.40)
    detector.prior_config = RetinaFacePriorConfig(
        min_sizes=((20,),),
        steps=(100,),
        variance=(0.1, 0.2),
    )
    detector.model_width = 100
    detector.model_height = 100
    detector._priors = np.asarray([[0.5, 0.5, 0.2, 0.2]], dtype=np.float32)
    detector._prior_boxes = MagicMock(side_effect=AssertionError("should not be called"))

    loc = np.zeros((1, 1, 4), dtype=np.float32)
    conf = np.asarray([[[0.0, 0.9]]], dtype=np.float32)
    landms = np.zeros((1, 1, 10), dtype=np.float32)

    decoded = detector._decode([loc, conf, landms], scale_x=1.0, scale_y=1.0)

    assert len(decoded) == 1
