from __future__ import annotations

from pathlib import Path
from typing import Sequence

from passport_core.config import Settings
from passport_core.io import EnjazCsvExporter, ImageLoader, SqliteResultStore, build_binary_store, encode_jpeg
from passport_core.llm import build_extractor
from passport_core.models import FaceDetectionResult, PassportData, PassportProcessingResult, ValidationResult
from passport_core.vision import PassportFaceDetector, PassportFeatureValidator


class PassportCoreService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

        self.loader = ImageLoader(
            timeout_seconds=self.settings.http_timeout_seconds,
            max_download_bytes=self.settings.max_download_bytes,
        )
        self.binary_store = build_binary_store(self.settings)
        self.result_store = SqliteResultStore(self.settings.sqlite_path)
        self.csv_exporter = EnjazCsvExporter()

        self.validator = PassportFeatureValidator(self.settings)
        self.face_detector = PassportFaceDetector(self.settings)
        self.extractor = build_extractor(self.settings)

    def close(self) -> None:
        self.loader.close()

    def process_source(self, source: str | Path) -> PassportProcessingResult:
        stored_original_uri: str | None = None
        stored_aligned_uri: str | None = None
        validation = ValidationResult(is_passport=False)
        face: FaceDetectionResult | None = None
        data: PassportData | None = None
        errors: list[str] = []

        try:
            loaded = self.loader.load(source)

            stored_original_uri = self.binary_store.save(
                loaded.data,
                folder="originals",
                filename=loaded.filename,
                content_type=loaded.mime_type,
            )

            match = self.validator.validate(loaded.bgr)
            validation = match.result

            if match.result.is_passport and match.aligned_bgr is not None:
                aligned_bytes = encode_jpeg(match.aligned_bgr)

                stored_aligned_uri = self.binary_store.save(
                    aligned_bytes,
                    folder="aligned",
                    filename="aligned.jpg",
                    content_type="image/jpeg",
                )

                face = self.face_detector.detect(
                    match.aligned_bgr,
                    match.homography_template_to_work,
                    match.work_to_original_scale,
                )

                data = self.extractor.extract(aligned_bytes, "image/jpeg")

            if match.result.is_passport and match.aligned_bgr is None:
                errors.append("Passport validated but alignment failed; extraction skipped.")

        except Exception as exc:
            errors.append(str(exc))

        result = PassportProcessingResult(
            source=str(source),
            stored_original_uri=stored_original_uri,
            stored_aligned_uri=stored_aligned_uri,
            validation=validation,
            face=face,
            data=data,
            errors=errors,
        )
        self.result_store.save(result)
        return result

    def process_sources(self, sources: Sequence[str | Path]) -> list[PassportProcessingResult]:
        return [self.process_source(source) for source in sources]

    def export_results_csv(self, results: Sequence[PassportProcessingResult], output_path: str | Path) -> None:
        self.csv_exporter.export(results, Path(output_path))

    def export_all_csv(self, output_path: str | Path) -> None:
        self.csv_exporter.export(self.result_store.fetch_all(), Path(output_path))
