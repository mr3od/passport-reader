from __future__ import annotations

import numpy as np

from passport_core.config import Settings
from passport_core.vision import PassportFaceDetector, PassportFeatureValidator


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
    assert match.homography_template_to_image is not None
    assert len(match.result.page_quad or []) == 4


def test_validator_rejects_blank(reference_template_path):
    settings = Settings(template_path=reference_template_path)
    validator = PassportFeatureValidator(settings)

    blank = np.zeros((400, 600, 3), dtype=np.uint8)
    match = validator.validate(blank)

    assert match.result.is_passport is False


def test_face_detector_maps_bbox_from_cropped_page_quad():
    detector = object.__new__(PassportFaceDetector)

    class StubDetector:
        def __init__(self) -> None:
            self.input_size = None

        def set_input_size(self, size):
            self.input_size = size

        setInputSize = set_input_size  # noqa: N815

        def detect(self, image):
            faces = np.asarray(
                [[5.0, 6.0, 20.0, 30.0, 0, 0, 0, 0, 0, 0, 0, 0.9]],
                dtype=np.float32,
            )
            return None, faces

    detector.detector = StubDetector()
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    face = detector.detect(image, [(50, 40), (150, 40), (150, 140), (50, 140)])

    assert detector.detector.input_size == (100, 100)
    assert face.bbox_original is not None
    assert face.bbox_original.x == 55
    assert face.bbox_original.y == 46
    assert face.bbox_original.width == 20
    assert face.bbox_original.height == 30
