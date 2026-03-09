from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from passport_core.config import Settings
from passport_core.io import encode_jpeg
from passport_core.models import (
    BoundingBox,
    FaceCropResult,
    FaceDetectionResult,
    ValidationDebug,
    ValidationResult,
)

ImageArray = NDArray[np.uint8]
FloatArray = NDArray[np.float64]


@dataclass(slots=True)
class PassportMatch:
    result: ValidationResult
    homography_template_to_image: FloatArray | None


class PassportFeatureValidator:
    """SIFT + FLANN based template matching on full-resolution inputs."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        template = cv2.imread(str(settings.template_path), cv2.IMREAD_COLOR)
        if template is None:
            raise FileNotFoundError(
                f"Masked passport template not found at {settings.template_path}"
            )

        self.template_bgr = template
        self.template_height, self.template_width = self.template_bgr.shape[:2]

        sift_create = getattr(cv2, "SIFT_create", None)
        if sift_create is None:
            raise RuntimeError("OpenCV build does not include SIFT support.")
        self.sift = cast(Any, sift_create)(nfeatures=settings.validator_sift_features)
        self.flann = cv2.FlannBasedMatcher(
            {"algorithm": 1, "trees": settings.validator_flann_trees},
            {"checks": settings.validator_flann_checks},
        )

        self.template_gray = self._to_gray(self.template_bgr)
        self.template_mask = self._build_template_mask(self.template_gray)
        self.template_keypoints, self.template_descriptors = self.sift.detectAndCompute(
            self.template_gray,
            self.template_mask,
        )

        if self.template_descriptors is None or len(self.template_keypoints) < 4:
            raise ValueError("Could not compute enough SIFT features for the template.")

    def validate(self, image_bgr: ImageArray) -> PassportMatch:
        image_gray = self._to_gray(image_bgr)

        keypoints, descriptors = self.sift.detectAndCompute(image_gray, None)
        if descriptors is None or self.template_descriptors is None:
            return self._invalid_match()
        if len(keypoints) < 4 or len(self.template_keypoints) < 4:
            return self._invalid_match()

        raw_matches = self.flann.knnMatch(descriptors, self.template_descriptors, k=2)
        good_matches: list[cv2.DMatch] = []
        for pair in raw_matches:
            if len(pair) != 2:
                continue
            m, n = pair
            if m.distance < self.settings.validator_ratio_test * n.distance:
                good_matches.append(m)

        if len(good_matches) < self.settings.validator_min_good_matches:
            return self._invalid_match(good_matches=len(good_matches))

        src_points = np.asarray(
            [keypoints[m.queryIdx].pt for m in good_matches],
            dtype=np.float32,
        ).reshape(-1, 1, 2)
        dst_points = np.asarray(
            [self.template_keypoints[m.trainIdx].pt for m in good_matches],
            dtype=np.float32,
        ).reshape(-1, 1, 2)

        homography, inlier_mask = cv2.findHomography(src_points, dst_points, cv2.RANSAC, 5.0)
        if homography is None or inlier_mask is None:
            return self._invalid_match(good_matches=len(good_matches))

        inliers = int(inlier_mask.ravel().sum())
        inlier_ratio = inliers / max(len(good_matches), 1)
        score = float(inliers) * inlier_ratio

        is_passport = (
            inliers >= self.settings.validator_min_inliers
            and inlier_ratio >= self.settings.validator_min_inlier_ratio
        )

        if not is_passport:
            return self._invalid_match(
                good_matches=len(good_matches),
                inliers=inliers,
                inlier_ratio=inlier_ratio,
                score=score,
            )

        corners = np.asarray(
            [
                [0, 0],
                [self.template_width, 0],
                [self.template_width, self.template_height],
                [0, self.template_height],
            ],
            dtype=np.float32,
        ).reshape(-1, 1, 2)
        projected = cv2.perspectiveTransform(corners, homography).reshape(-1, 2)
        page_quad = [(int(round(x)), int(round(y))) for x, y in projected]

        return PassportMatch(
            result=ValidationResult(
                is_passport=True,
                page_quad=page_quad,
                debug=ValidationDebug(
                    good_matches=len(good_matches),
                    inliers=inliers,
                    inlier_ratio=inlier_ratio,
                    score=score,
                ),
            ),
            homography_template_to_image=homography.astype(np.float64),
        )

    @staticmethod
    def _to_gray(image_bgr: NDArray[Any]) -> ImageArray:
        if image_bgr.ndim == 2:
            return image_bgr
        return cast(ImageArray, cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY))

    @staticmethod
    def _build_template_mask(template_gray: ImageArray) -> ImageArray:
        # Keep non-black template regions as feature mask.
        _, mask = cv2.threshold(template_gray, 8, 255, cv2.THRESH_BINARY)
        return cast(ImageArray, mask)

    def _invalid_match(
        self,
        *,
        good_matches: int = 0,
        inliers: int = 0,
        inlier_ratio: float = 0.0,
        score: float = 0.0,
    ) -> PassportMatch:
        return PassportMatch(
            result=ValidationResult(
                is_passport=False,
                page_quad=None,
                debug=ValidationDebug(
                    good_matches=good_matches,
                    inliers=inliers,
                    inlier_ratio=inlier_ratio,
                    score=score,
                ),
            ),
            homography_template_to_image=None,
        )


class PassportFaceDetector:
    def __init__(self, settings: Settings) -> None:
        if not hasattr(cv2, "FaceDetectorYN_create"):
            raise RuntimeError("OpenCV build does not include FaceDetectorYN support.")

        if not settings.face_model_path.exists():
            raise FileNotFoundError(f"YuNet face model not found at {settings.face_model_path}")

        self.detector = cv2.FaceDetectorYN_create(
            str(settings.face_model_path),
            "",
            (320, 320),
            settings.face_score_threshold,
            0.3,
            5000,
        )

    def detect(
        self,
        image_bgr: ImageArray,
        page_quad: list[tuple[int, int]] | None = None,
    ) -> FaceDetectionResult:
        detection_image = image_bgr
        offset_x = 0
        offset_y = 0

        if page_quad:
            cropped = self._crop_to_page_quad(image_bgr, page_quad)
            if cropped is not None:
                detection_image, offset_x, offset_y = cropped

        self.detector.setInputSize((detection_image.shape[1], detection_image.shape[0]))
        _, faces = self.detector.detect(detection_image)

        if faces is None or len(faces) == 0:
            return FaceDetectionResult()

        best = max(faces, key=lambda row: float(row[2] * row[3] * row[-1]))
        bbox = self._bbox_from_face_row(best, offset_x=offset_x, offset_y=offset_y)
        return FaceDetectionResult(bbox_aligned=None, bbox_original=bbox)

    @staticmethod
    def _crop_to_page_quad(
        image_bgr: ImageArray,
        page_quad: list[tuple[int, int]],
    ) -> tuple[ImageArray, int, int] | None:
        points = np.asarray(page_quad, dtype=np.int32)
        if points.shape != (4, 2):
            return None

        height, width = image_bgr.shape[:2]
        min_x = max(0, int(points[:, 0].min()))
        min_y = max(0, int(points[:, 1].min()))
        max_x = min(width, int(points[:, 0].max()))
        max_y = min(height, int(points[:, 1].max()))

        if min_x >= max_x or min_y >= max_y:
            return None

        cropped = image_bgr[min_y:max_y, min_x:max_x].copy()
        shifted = points - np.array([[min_x, min_y]], dtype=np.int32)
        mask = np.zeros(cropped.shape[:2], dtype=np.uint8)
        cv2.fillConvexPoly(mask, shifted, 255)
        cropped[mask == 0] = 0
        return cropped, min_x, min_y

    def _bbox_from_face_row(
        self,
        row: NDArray[np.float32],
        *,
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> BoundingBox:
        x, y, width, height = row[:4]
        score = float(row[-1])

        return BoundingBox(
            x=max(0, int(round(float(x))) + offset_x),
            y=max(0, int(round(float(y))) + offset_y),
            width=max(0, int(round(float(width)))),
            height=max(0, int(round(float(height)))),
            score=score,
        )


class PassportFaceCropper:
    def crop(
        self,
        image_bgr: ImageArray,
        bbox: BoundingBox | None,
    ) -> FaceCropResult | None:
        if bbox is None:
            return None

        image_height, image_width = image_bgr.shape[:2]
        x0 = max(0, bbox.x)
        y0 = max(0, bbox.y)
        x1 = min(image_width, bbox.x + bbox.width)
        y1 = min(image_height, bbox.y + bbox.height)

        if x0 >= x1 or y0 >= y1:
            return None

        cropped = image_bgr[y0:y1, x0:x1].copy()
        if cropped.size == 0:
            return None

        return FaceCropResult(
            bbox_original=BoundingBox(
                x=x0,
                y=y0,
                width=x1 - x0,
                height=y1 - y0,
                score=bbox.score,
            ),
            width=x1 - x0,
            height=y1 - y0,
            jpeg_bytes=encode_jpeg(cropped),
        )
