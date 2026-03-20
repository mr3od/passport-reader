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
    homography_image_to_template: FloatArray | None


@dataclass(slots=True)
class RetinaFacePriorConfig:
    min_sizes: tuple[tuple[int, ...], ...] = ((16, 32), (64, 128), (256, 512))
    steps: tuple[int, ...] = (8, 16, 32)
    variance: tuple[float, float] = (0.1, 0.2)


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

        homography, inlier_mask = cv2.findHomography(
            src_points,
            dst_points,
            cv2.RANSAC,
            self.settings.validator_ransac_threshold,
        )
        if homography is None or inlier_mask is None:
            return self._invalid_match(good_matches=len(good_matches))

        determinant = float(np.linalg.det(homography))
        if abs(determinant) < 1e-6 or determinant < 0:
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
        template_to_image = np.linalg.inv(homography)
        projected: NDArray[np.float32] = np.asarray(
            cv2.perspectiveTransform(corners, template_to_image).reshape(-1, 2),
            dtype=np.float32,
        )
        if not self._is_valid_projected_quad(projected, image_bgr.shape):
            return self._invalid_match(
                good_matches=len(good_matches),
                inliers=inliers,
                inlier_ratio=inlier_ratio,
                score=score,
            )
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
            homography_image_to_template=homography.astype(np.float64),
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

    def _is_valid_projected_quad(
        self,
        projected: NDArray[np.float32],
        image_shape: tuple[int, ...],
    ) -> bool:
        quad_int = projected.reshape(-1, 1, 2).astype(np.int32)
        if not cv2.isContourConvex(quad_int):
            return False

        image_area = image_shape[0] * image_shape[1]
        quad_area = cv2.contourArea(projected.astype(np.float32))
        if quad_area <= 0:
            return False

        ratio = quad_area / float(image_area)
        return (
            self.settings.validator_min_quad_area_ratio
            <= ratio
            <= self.settings.validator_max_quad_area_ratio
        )

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
            homography_image_to_template=None,
        )


class RetinaFaceDetector:
    def __init__(self, settings: Settings) -> None:
        if not settings.face_model_path.exists():
            raise FileNotFoundError(
                f"RetinaFace ONNX model not found at {settings.face_model_path}"
            )

        import onnxruntime as ort

        self.settings = settings
        self.prior_config = RetinaFacePriorConfig()
        self.session = ort.InferenceSession(
            str(settings.face_model_path),
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name
        self.model_width, self.model_height = self._resolve_input_size()
        self._priors = self._prior_boxes()

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

        batched, scale_x, scale_y = self._preprocess(detection_image)
        outputs = self.session.run(
            None,
            {self.input_name: batched},
        )
        decoded = self._decode(outputs, scale_x=scale_x, scale_y=scale_y)
        if not decoded:
            return FaceDetectionResult()

        best = max(
            decoded,
            key=lambda row: float(max(0.0, row[2] - row[0]) * max(0.0, row[3] - row[1]) * row[4]),
        )
        bbox = self._bbox_from_xyxy(
            best[:4],
            score=float(best[4]),
            offset_x=offset_x,
            offset_y=offset_y,
        )
        landmarks = self._landmarks_from_decoded(
            best,
            offset_x=offset_x,
            offset_y=offset_y,
        )
        return FaceDetectionResult(
            bbox_aligned=None,
            bbox_original=bbox,
            landmarks_original=landmarks,
        )

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
        cv2.fillPoly(mask, [shifted], 255)
        cropped[mask == 0] = 0
        return cropped, min_x, min_y

    @staticmethod
    def _bbox_from_xyxy(
        xyxy: NDArray[np.float32],
        *,
        score: float,
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> BoundingBox:
        x1, y1, x2, y2 = xyxy[:4]
        width = max(0.0, float(x2) - float(x1))
        height = max(0.0, float(y2) - float(y1))

        return BoundingBox(
            x=max(0, int(round(float(x1))) + offset_x),
            y=max(0, int(round(float(y1))) + offset_y),
            width=max(0, int(round(width))),
            height=max(0, int(round(height))),
            score=score,
        )

    def _resolve_input_size(self) -> tuple[int, int]:
        input_shape = self.session.get_inputs()[0].shape
        width = input_shape[-1]
        height = input_shape[-2]
        resolved_width = (
            int(width) if isinstance(width, int) and width > 0 else self.settings.face_input_width
        )
        resolved_height = (
            int(height)
            if isinstance(height, int) and height > 0
            else self.settings.face_input_height
        )
        return resolved_width, resolved_height

    def _preprocess(self, image_bgr: ImageArray) -> tuple[NDArray[np.float32], float, float]:
        resized = cv2.resize(
            image_bgr,
            (self.model_width, self.model_height),
            interpolation=cv2.INTER_LINEAR,
        )
        blob = resized.astype(np.float32)
        blob -= np.asarray([104.0, 117.0, 123.0], dtype=np.float32)
        blob = np.transpose(blob, (2, 0, 1))
        blob = np.expand_dims(blob, axis=0)
        scale_x = image_bgr.shape[1] / self.model_width
        scale_y = image_bgr.shape[0] / self.model_height
        return blob, float(scale_x), float(scale_y)

    def _decode(
        self,
        outputs: list[Any],
        *,
        scale_x: float,
        scale_y: float,
    ) -> list[NDArray[np.float32]]:
        if len(outputs) < 3:
            raise ValueError("RetinaFace ONNX model must return bbox, conf, and landmark outputs.")

        loc, conf, landms = (np.asarray(output) for output in outputs[:3])
        priors = self._priors

        loc = np.squeeze(loc, axis=0)
        conf = np.squeeze(conf, axis=0)
        landms = np.squeeze(landms, axis=0)
        if conf.ndim != 2 or conf.shape[1] < 2:
            raise ValueError("RetinaFace confidence output shape is unsupported.")

        scores = conf[:, 1]
        keep = scores >= self.settings.face_score_threshold
        if not np.any(keep):
            return []

        priors = priors[keep]
        loc = loc[keep]
        scores = scores[keep]
        landms = landms[keep]

        boxes = self._decode_boxes(loc, priors)
        decoded_landms = self._decode_landmarks(landms, priors)
        boxes[:, 0] *= self.model_width * scale_x
        boxes[:, 1] *= self.model_height * scale_y
        boxes[:, 2] *= self.model_width * scale_x
        boxes[:, 3] *= self.model_height * scale_y
        decoded_landms[:, 0::2] *= self.model_width * scale_x
        decoded_landms[:, 1::2] *= self.model_height * scale_y

        detections = np.concatenate([boxes, scores[:, None], decoded_landms], axis=1).astype(
            np.float32
        )
        keep_indices = self._nms(detections, self.settings.face_nms_threshold)
        return [detections[index] for index in keep_indices]

    def _prior_boxes(self) -> NDArray[np.float32]:
        priors: list[list[float]] = []
        for min_sizes, step in zip(
            self.prior_config.min_sizes,
            self.prior_config.steps,
            strict=True,
        ):
            feature_height = int(np.ceil(self.model_height / step))
            feature_width = int(np.ceil(self.model_width / step))
            for i in range(feature_height):
                for j in range(feature_width):
                    for min_size in min_sizes:
                        s_kx = min_size / self.model_width
                        s_ky = min_size / self.model_height
                        cx = (j + 0.5) * step / self.model_width
                        cy = (i + 0.5) * step / self.model_height
                        priors.append([cx, cy, s_kx, s_ky])
        return np.asarray(priors, dtype=np.float32)

    def _decode_boxes(
        self,
        loc: NDArray[np.float32],
        priors: NDArray[np.float32],
    ) -> NDArray[np.float32]:
        variance0, variance1 = self.prior_config.variance
        boxes = np.empty_like(loc, dtype=np.float32)
        boxes[:, :2] = priors[:, :2] + loc[:, :2] * variance0 * priors[:, 2:]
        boxes[:, 2:] = priors[:, 2:] * np.exp(loc[:, 2:] * variance1)
        boxes[:, :2] -= boxes[:, 2:] / 2
        boxes[:, 2:] += boxes[:, :2]
        return boxes

    def _decode_landmarks(
        self,
        landms: NDArray[np.float32],
        priors: NDArray[np.float32],
    ) -> NDArray[np.float32]:
        variance0 = self.prior_config.variance[0]
        centers = np.tile(priors[:, :2], (1, 5))
        sizes = np.tile(priors[:, 2:], (1, 5))
        return (centers + landms * variance0 * sizes).astype(np.float32)

    @staticmethod
    def _landmarks_from_decoded(
        detection: NDArray[np.float32],
        *,
        offset_x: int,
        offset_y: int,
    ) -> list[tuple[int, int]] | None:
        if detection.shape[0] < 15:
            return None
        landmarks: list[tuple[int, int]] = []
        for index in range(5):
            x = int(round(float(detection[5 + index * 2]))) + offset_x
            y = int(round(float(detection[6 + index * 2]))) + offset_y
            landmarks.append((x, y))
        return landmarks

    @staticmethod
    def _nms(detections: NDArray[np.float32], threshold: float) -> list[int]:
        x1 = detections[:, 0]
        y1 = detections[:, 1]
        x2 = detections[:, 2]
        y2 = detections[:, 3]
        scores = detections[:, 4]

        areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
        order = scores.argsort()[::-1]
        keep: list[int] = []

        while order.size > 0:
            index = int(order[0])
            keep.append(index)
            if order.size == 1:
                break

            rest = order[1:]
            xx1 = np.maximum(x1[index], x1[rest])
            yy1 = np.maximum(y1[index], y1[rest])
            xx2 = np.minimum(x2[index], x2[rest])
            yy2 = np.minimum(y2[index], y2[rest])

            width = np.maximum(0.0, xx2 - xx1)
            height = np.maximum(0.0, yy2 - yy1)
            intersection = width * height
            union = areas[index] + areas[rest] - intersection
            overlap = np.where(union > 0.0, intersection / union, 0.0)
            order = rest[overlap <= threshold]

        return keep


PassportFaceDetector = RetinaFaceDetector


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
