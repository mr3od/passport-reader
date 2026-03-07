from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from passport_core.config import Settings
from passport_core.models import BoundingBox, FaceDetectionResult, ValidationDebug, ValidationResult

ImageArray = NDArray[np.uint8]
FloatArray = NDArray[np.float64]


@dataclass(slots=True)
class PassportMatch:
    result: ValidationResult
    aligned_bgr: ImageArray | None
    homography_template_to_work: FloatArray | None
    work_to_original_scale: float


class PassportFeatureValidator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        template = cv2.imread(str(settings.template_path), cv2.IMREAD_COLOR)
        if template is None:
            raise FileNotFoundError(f"Masked passport template not found at {settings.template_path}")

        self.template_bgr = template
        self.template_height, self.template_width = self.template_bgr.shape[:2]

        self.orb = cv2.ORB_create(
            nfeatures=settings.validator_max_features,
            scaleFactor=1.2,
            nlevels=8,
        )
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        template_processed = self._preprocess(self.template_bgr)
        self.template_keypoints, self.template_descriptors = self.orb.detectAndCompute(
            template_processed, None
        )

        if self.template_descriptors is None or not self.template_keypoints:
            raise ValueError("Could not compute features for the masked passport template.")

    def validate(self, image_bgr: ImageArray) -> PassportMatch:
        work_image, work_to_original_scale = self._resize_for_features(image_bgr)
        work_processed = self._preprocess(work_image)

        keypoints, descriptors = self.orb.detectAndCompute(work_processed, None)
        if descriptors is None or not keypoints:
            return self._invalid_match()

        raw_matches = self.matcher.knnMatch(self.template_descriptors, descriptors, k=2)
        good_matches = []
        for pair in raw_matches:
            if len(pair) != 2:
                continue
            first, second = pair
            if first.distance < self.settings.validator_ratio_test * second.distance:
                good_matches.append(first)

        if len(good_matches) < self.settings.validator_min_good_matches:
            return self._invalid_match(good_matches=len(good_matches))

        src_points = np.float32([self.template_keypoints[m.queryIdx].pt for m in good_matches]).reshape(
            -1, 1, 2
        )
        dst_points = np.float32([keypoints[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

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

        corners = np.float32(
            [
                [0, 0],
                [self.template_width, 0],
                [self.template_width, self.template_height],
                [0, self.template_height],
            ]
        ).reshape(-1, 1, 2)

        projected = cv2.perspectiveTransform(corners, homography).reshape(-1, 2)
        page_quad = [
            (int(round(x * work_to_original_scale)), int(round(y * work_to_original_scale)))
            for x, y in projected
        ]

        aligned_bgr = None
        try:
            inverse_h = np.linalg.inv(homography)
            aligned_bgr = cv2.warpPerspective(
                work_image,
                inverse_h,
                (self.template_width, self.template_height),
            )
        except np.linalg.LinAlgError:
            aligned_bgr = None

        if aligned_bgr is None:
            return self._invalid_match(
                good_matches=len(good_matches),
                inliers=inliers,
                inlier_ratio=inlier_ratio,
                score=score,
            )

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
            aligned_bgr=aligned_bgr,
            homography_template_to_work=homography.astype(np.float64),
            work_to_original_scale=work_to_original_scale,
        )

    def _resize_for_features(self, image_bgr: ImageArray) -> tuple[ImageArray, float]:
        height, width = image_bgr.shape[:2]
        max_dim = max(height, width)

        if max_dim <= self.settings.validator_max_dimension:
            return image_bgr, 1.0

        scale = self.settings.validator_max_dimension / max_dim
        resized = cv2.resize(
            image_bgr,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
        return resized, 1.0 / scale

    def _preprocess(self, image_bgr: ImageArray) -> ImageArray:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        return self.clahe.apply(blurred)

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
            aligned_bgr=None,
            homography_template_to_work=None,
            work_to_original_scale=1.0,
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
        aligned_bgr: ImageArray,
        homography_template_to_work: FloatArray | None,
        work_to_original_scale: float,
    ) -> FaceDetectionResult:
        self.detector.setInputSize((aligned_bgr.shape[1], aligned_bgr.shape[0]))
        _, faces = self.detector.detect(aligned_bgr)

        if faces is None or len(faces) == 0:
            return FaceDetectionResult()

        best = max(faces, key=lambda row: float(row[2] * row[3] * row[-1]))
        aligned_box = self._bbox_from_face_row(best)

        original_box = None
        if homography_template_to_work is not None:
            corners = np.array(
                [
                    [[aligned_box.x, aligned_box.y]],
                    [[aligned_box.x + aligned_box.width, aligned_box.y]],
                    [[aligned_box.x + aligned_box.width, aligned_box.y + aligned_box.height]],
                    [[aligned_box.x, aligned_box.y + aligned_box.height]],
                ],
                dtype=np.float32,
            )
            mapped = cv2.perspectiveTransform(corners, homography_template_to_work.astype(np.float32)).reshape(
                -1, 2
            )
            mapped *= work_to_original_scale

            min_x, min_y = mapped.min(axis=0)
            max_x, max_y = mapped.max(axis=0)

            original_box = BoundingBox(
                x=int(round(min_x)),
                y=int(round(min_y)),
                width=max(0, int(round(max_x - min_x))),
                height=max(0, int(round(max_y - min_y))),
                score=aligned_box.score,
            )

        return FaceDetectionResult(bbox_aligned=aligned_box, bbox_original=original_box)

    def _bbox_from_face_row(self, row: NDArray[np.float32]) -> BoundingBox:
        x, y, width, height = row[:4]
        score = float(row[-1])

        return BoundingBox(
            x=max(0, int(round(float(x)))),
            y=max(0, int(round(float(y)))),
            width=max(0, int(round(float(width)))),
            height=max(0, int(round(float(height)))),
            score=score,
        )
