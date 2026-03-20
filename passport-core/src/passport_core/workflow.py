from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from passport_core.config import Settings
from passport_core.io import ImageArray, ImageLoader, LoadedImage, encode_jpeg, load_image_bytes
from passport_core.llm import PassportExtractor, build_extractor
from passport_core.models import (
    BoundingBox,
    FaceCropResult,
    FaceDetectionResult,
    PassportData,
    ValidationResult,
)
from passport_core.vision import PassportFaceCropper, PassportFaceDetector, PassportFeatureValidator

type ImageInput = LoadedImage | ImageArray

PASSPORT_SCORE_BONUS = 10_000.0
FACE_SCORE_BONUS = 1_000.0
FACE_CONFIDENCE_WEIGHT = 100.0
FACE_AREA_DIVISOR = 100.0
LANDMARK_SCORE_WEIGHT = 500.0
FACE_CROP_BONUS = 100_000.0


@dataclass(slots=True)
class _WorkflowCandidate:
    name: str
    image_bgr: ImageArray
    validation: ValidationResult
    loaded: LoadedImage | None = None
    face: FaceDetectionResult | None = None
    face_crop: FaceCropResult | None = None

    @property
    def score(self) -> float:
        score = float(self.validation.debug.score)
        if not self.validation.is_passport:
            return score
        score += PASSPORT_SCORE_BONUS
        if self.face is not None and self.face.bbox_original is not None:
            bbox = self.face.bbox_original
            area = max(0, bbox.width) * max(0, bbox.height)
            score += FACE_SCORE_BONUS
            score += float(bbox.score or 0.0) * FACE_CONFIDENCE_WEIGHT
            score += area / FACE_AREA_DIVISOR
            score += self.landmark_orientation_score * LANDMARK_SCORE_WEIGHT
        if self.face_crop is not None:
            score += FACE_CROP_BONUS
        return score

    @property
    def landmark_orientation_score(self) -> float:
        landmarks = self.face.landmarks_original if self.face is not None else None
        if landmarks is None or len(landmarks) != 5:
            return 0.0

        left_eye, right_eye, nose, left_mouth, right_mouth = landmarks
        eyes_y = (left_eye[1] + right_eye[1]) / 2.0
        mouth_y = (left_mouth[1] + right_mouth[1]) / 2.0

        score = 0.0
        if left_eye[0] < right_eye[0]:
            score += 0.25
        if eyes_y < nose[1]:
            score += 0.25
        if nose[1] < mouth_y:
            score += 0.25
        if left_mouth[0] < right_mouth[0]:
            score += 0.25
        return score


@dataclass(slots=True)
class PassportWorkflowResult:
    """Transport-neutral result returned by the public adapter workflow."""

    loaded: LoadedImage
    validation: ValidationResult
    processed_loaded: LoadedImage | None = None
    face: FaceDetectionResult | None = None
    face_crop: FaceCropResult | None = None
    data: PassportData | None = None

    @property
    def source(self) -> str:
        return self.loaded.source

    @property
    def filename(self) -> str:
        return self.loaded.filename

    @property
    def mime_type(self) -> str:
        return self.loaded.mime_type

    @property
    def image_bytes(self) -> bytes:
        return self.loaded.data

    @property
    def processed_image_bytes(self) -> bytes:
        selected = self.processed_loaded or self.loaded
        return selected.data

    @property
    def face_crop_bytes(self) -> bytes | None:
        if self.face_crop is None:
            return None
        return self.face_crop.jpeg_bytes

    @property
    def has_face_crop(self) -> bool:
        return self.face_crop is not None

    @property
    def is_complete(self) -> bool:
        return self.validation.is_passport and self.face_crop is not None and self.data is not None


class PassportWorkflow:
    """Adapter-facing public API for transport-neutral passport processing."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        loader: ImageLoader | None = None,
        validator: PassportFeatureValidator | None = None,
        face_detector: PassportFaceDetector | None = None,
        face_cropper: PassportFaceCropper | None = None,
        extractor: PassportExtractor | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.loader = loader or ImageLoader(
            timeout_seconds=self.settings.http_timeout_seconds,
            max_download_bytes=self.settings.max_download_bytes,
        )
        self.validator = validator or PassportFeatureValidator(self.settings)
        self.face_detector = face_detector or PassportFaceDetector(self.settings)
        self.face_cropper = face_cropper or PassportFaceCropper()
        self.extractor = extractor or build_extractor(self.settings)

    def close(self) -> None:
        self.loader.close()

    def load_source(self, source: str | Path) -> LoadedImage:
        return self.loader.load(source)

    def load_bytes(
        self,
        data: bytes,
        *,
        filename: str = "upload.jpg",
        mime_type: str = "image/jpeg",
        source: str | None = None,
    ) -> LoadedImage:
        return load_image_bytes(
            data,
            filename=filename,
            mime_type=mime_type,
            source=source,
        )

    def validate_passport(self, image: ImageInput) -> ValidationResult:
        return self.validator.validate(self._image_bgr(image)).result

    def detect_face(
        self,
        image: ImageInput,
        page_quad: list[tuple[int, int]] | None = None,
    ) -> FaceDetectionResult:
        return self.face_detector.detect(self._image_bgr(image), page_quad)

    def crop_face(
        self,
        image: ImageInput,
        bbox: BoundingBox | None,
    ) -> FaceCropResult | None:
        return self.face_cropper.crop(self._image_bgr(image), bbox)

    def extract_data(
        self,
        image: LoadedImage | bytes,
        mime_type: str = "image/jpeg",
    ) -> PassportData:
        if isinstance(image, LoadedImage):
            return self.extractor.extract(image.data, image.mime_type)
        return self.extractor.extract(image, mime_type)

    def process_loaded(self, loaded: LoadedImage) -> PassportWorkflowResult:
        candidates = self._evaluate_candidates(loaded)
        result = self._build_result_from_candidates(loaded, candidates)

        first_exc: Exception | None = None
        last_exc: Exception | None = None
        crop_candidates = [candidate for candidate in candidates if candidate.face_crop is not None]
        for candidate in crop_candidates[: self.settings.candidate_max_extraction_attempts]:
            candidate_loaded = self._promote_candidate(loaded, candidate)
            result = self._build_result_from_candidates(loaded, [candidate])
            result.processed_loaded = candidate_loaded
            try:
                result.data = self.extract_data(candidate_loaded)
                return result
            except Exception as exc:
                if first_exc is None:
                    first_exc = exc
                last_exc = exc

        if first_exc is not None:
            raise first_exc from last_exc
        return result

    def prepare_loaded(self, loaded: LoadedImage) -> PassportWorkflowResult:
        return self._build_result_from_candidates(loaded, self._evaluate_candidates(loaded))

    def process_source(self, source: str | Path) -> PassportWorkflowResult:
        return self.process_loaded(self.load_source(source))

    def process_bytes(
        self,
        data: bytes,
        *,
        filename: str = "upload.jpg",
        mime_type: str = "image/jpeg",
        source: str | None = None,
    ) -> PassportWorkflowResult:
        return self.process_loaded(
            self.load_bytes(
                data,
                filename=filename,
                mime_type=mime_type,
                source=source,
            )
        )

    @staticmethod
    def _image_bgr(image: ImageInput) -> ImageArray:
        if isinstance(image, LoadedImage):
            return image.bgr
        return image

    def _evaluate_candidates(self, loaded: LoadedImage) -> list[_WorkflowCandidate]:
        candidates: list[_WorkflowCandidate] = []
        for name, image_bgr in self._transform_variants(loaded.bgr):
            evaluation_image: ImageInput = loaded if name == "identity" else image_bgr
            validation = self.validate_passport(evaluation_image)
            candidate = _WorkflowCandidate(
                name=name,
                image_bgr=image_bgr,
                validation=validation,
            )
            if validation.is_passport:
                candidate.face = self.detect_face(evaluation_image, validation.page_quad)
                candidate.face_crop = self.crop_face(
                    evaluation_image,
                    candidate.face.bbox_original,
                )
            candidates.append(candidate)
            if self._should_early_stop(candidate):
                break

        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        return candidates

    def _promote_candidate(
        self,
        original_loaded: LoadedImage,
        candidate: _WorkflowCandidate,
    ) -> LoadedImage:
        if candidate.loaded is None:
            candidate.loaded = self._make_candidate_loaded(
                original_loaded,
                name=candidate.name,
                image_bgr=candidate.image_bgr,
            )
        return candidate.loaded

    def _build_result_from_candidates(
        self,
        loaded: LoadedImage,
        candidates: list[_WorkflowCandidate],
    ) -> PassportWorkflowResult:
        if not candidates:
            return PassportWorkflowResult(
                loaded=loaded,
                validation=ValidationResult(is_passport=False),
            )

        best = candidates[0]
        best_loaded = self._promote_candidate(loaded, best)
        return PassportWorkflowResult(
            loaded=loaded,
            processed_loaded=best_loaded,
            validation=self._validation_in_original_coordinates(
                best.validation,
                best.name,
                loaded.bgr.shape,
            ),
            face=self._face_in_original_coordinates(
                best.face,
                best.name,
                loaded.bgr.shape,
            ),
            face_crop=self._face_crop_in_original_coordinates(
                best.face_crop,
                best.name,
                loaded.bgr.shape,
            ),
        )

    def _validation_in_original_coordinates(
        self,
        validation: ValidationResult,
        transform_name: str,
        original_shape: tuple[int, ...],
    ) -> ValidationResult:
        if transform_name == "identity" or validation.page_quad is None:
            return validation
        return validation.model_copy(
            update={
                "page_quad": self._points_to_original(
                    transform_name,
                    validation.page_quad,
                    original_shape,
                )
            }
        )

    def _face_in_original_coordinates(
        self,
        face: FaceDetectionResult | None,
        transform_name: str,
        original_shape: tuple[int, ...],
    ) -> FaceDetectionResult | None:
        if face is None or transform_name == "identity":
            return face
        return face.model_copy(
            update={
                "bbox_aligned": self._bbox_to_original(
                    face.bbox_aligned,
                    transform_name,
                    original_shape,
                ),
                "bbox_original": self._bbox_to_original(
                    face.bbox_original,
                    transform_name,
                    original_shape,
                ),
                "landmarks_original": self._points_to_original(
                    transform_name,
                    face.landmarks_original,
                    original_shape,
                )
                if face.landmarks_original is not None
                else None,
            }
        )

    def _face_crop_in_original_coordinates(
        self,
        crop: FaceCropResult | None,
        transform_name: str,
        original_shape: tuple[int, ...],
    ) -> FaceCropResult | None:
        if crop is None or transform_name == "identity":
            return crop
        return crop.model_copy(
            update={
                "bbox_original": self._bbox_to_original(
                    crop.bbox_original,
                    transform_name,
                    original_shape,
                )
            }
        )

    @staticmethod
    def _make_candidate_loaded(
        original_loaded: LoadedImage,
        *,
        name: str,
        image_bgr: ImageArray,
    ) -> LoadedImage:
        if name == "identity":
            return original_loaded

        data = encode_jpeg(image_bgr)
        filename = f"{Path(original_loaded.filename).stem}_{name}.jpg"
        return LoadedImage(
            source=f"{original_loaded.source}#{name}",
            data=data,
            mime_type="image/jpeg",
            filename=filename,
            bgr=image_bgr,
        )

    def _should_early_stop(self, candidate: _WorkflowCandidate) -> bool:
        if not candidate.validation.is_passport or candidate.face_crop is None:
            return False
        bbox = candidate.face.bbox_original if candidate.face is not None else None
        face_score = float(bbox.score or 0.0) if bbox is not None else 0.0
        return (
            candidate.validation.debug.score >= self.settings.candidate_early_stop_validation_score
            and face_score >= self.settings.candidate_early_stop_face_score
            and candidate.landmark_orientation_score
            >= self.settings.candidate_early_stop_landmark_score
        )

    @staticmethod
    def _transform_variants(image_bgr: ImageArray) -> list[tuple[str, ImageArray]]:
        variants = [
            ("identity", image_bgr),
            ("rot180", cv2.rotate(image_bgr, cv2.ROTATE_180)),
            ("rot90", cv2.rotate(image_bgr, cv2.ROTATE_90_CLOCKWISE)),
            ("rot270", cv2.rotate(image_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)),
            ("flip_h", cv2.flip(image_bgr, 1)),
            ("flip_v", cv2.flip(image_bgr, 0)),
            ("transpose", cv2.transpose(image_bgr)),
            ("transverse", cv2.flip(cv2.transpose(image_bgr), -1)),
        ]
        return [(name, np.ascontiguousarray(variant)) for name, variant in variants]

    @classmethod
    def _points_to_original(
        cls,
        transform_name: str,
        points: list[tuple[int, int]] | None,
        original_shape: tuple[int, ...],
    ) -> list[tuple[int, int]] | None:
        if points is None:
            return None
        return [
            cls._point_to_original(transform_name, point[0], point[1], original_shape)
            for point in points
        ]

    @staticmethod
    def _point_to_original(
        transform_name: str,
        x: int,
        y: int,
        original_shape: tuple[int, ...],
    ) -> tuple[int, int]:
        height, width = original_shape[:2]
        if transform_name == "identity":
            return (x, y)
        if transform_name == "rot180":
            return (width - 1 - x, height - 1 - y)
        if transform_name == "rot90":
            return (y, height - 1 - x)
        if transform_name == "rot270":
            return (width - 1 - y, x)
        if transform_name == "flip_h":
            return (width - 1 - x, y)
        if transform_name == "flip_v":
            return (x, height - 1 - y)
        if transform_name == "transpose":
            return (y, x)
        if transform_name == "transverse":
            return (width - 1 - y, height - 1 - x)
        raise ValueError(f"Unsupported transform: {transform_name}")

    @classmethod
    def _bbox_to_original(
        cls,
        bbox: BoundingBox | None,
        transform_name: str,
        original_shape: tuple[int, ...],
    ) -> BoundingBox | None:
        if bbox is None:
            return None
        mapped = cls._points_to_original(
            transform_name,
            [
                (bbox.x, bbox.y),
                (bbox.x + bbox.width, bbox.y),
                (bbox.x + bbox.width, bbox.y + bbox.height),
                (bbox.x, bbox.y + bbox.height),
            ],
            original_shape,
        )
        assert mapped is not None
        xs = [point[0] for point in mapped]
        ys = [point[1] for point in mapped]
        return BoundingBox(
            x=min(xs),
            y=min(ys),
            width=max(xs) - min(xs),
            height=max(ys) - min(ys),
            score=bbox.score,
        )
