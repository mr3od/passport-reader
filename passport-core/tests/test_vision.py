from __future__ import annotations

import numpy as np

from passport_core.config import Settings
from passport_core.vision import PassportFeatureValidator


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
    assert match.aligned_bgr is not None
    assert len(match.result.page_quad or []) == 4


def test_validator_rejects_blank(reference_template_path):
    settings = Settings(template_path=reference_template_path)
    validator = PassportFeatureValidator(settings)

    blank = np.zeros((400, 600, 3), dtype=np.uint8)
    match = validator.validate(blank)

    assert match.result.is_passport is False
