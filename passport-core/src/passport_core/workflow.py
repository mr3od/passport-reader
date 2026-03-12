from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from passport_core.config import Settings
from passport_core.io import ImageArray, ImageLoader, LoadedImage, load_image_bytes
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


@dataclass(slots=True)
class PassportWorkflowResult:
    """Transport-neutral result returned by the public adapter workflow."""

    loaded: LoadedImage
    validation: ValidationResult
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
    def face_crop_bytes(self) -> bytes | None:
        if self.face_crop is None:
            return None
        return self.face_crop.jpeg_bytes

    @property
    def has_face_crop(self) -> bool:
        return self.face_crop is not None

    @property
    def is_complete(self) -> bool:
        return (
            self.validation.is_passport
            and self.face_crop is not None
            and self.data is not None
        )


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
        validation = self.validate_passport(loaded)
        result = PassportWorkflowResult(loaded=loaded, validation=validation)
        if not validation.is_passport:
            return result

        face = self.detect_face(loaded, validation.page_quad)
        result.face = face

        crop = self.crop_face(loaded, face.bbox_original)
        result.face_crop = crop
        if crop is None:
            return result

        result.data = self.extract_data(loaded)
        return result

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
