from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from passport_core.config import Settings
from passport_core.errors import ErrorCode, ExtractionError, FaceDetectionError, StorageError
from passport_core.io import (
    EnjazCsvExporter,
    ImageLoader,
    build_binary_store,
    build_result_store,
    encode_jpeg,
)
from passport_core.llm import build_extractor
from passport_core.log import bind_logger
from passport_core.models import (
    FaceDetectionResult,
    PassportData,
    PassportProcessingResult,
    ProcessingError,
    ValidationResult,
)
from passport_core.vision import PassportFaceDetector, PassportFeatureValidator


class PassportCoreService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

        self.loader = ImageLoader(
            timeout_seconds=self.settings.http_timeout_seconds,
            max_download_bytes=self.settings.max_download_bytes,
        )
        self.binary_store = build_binary_store(self.settings)
        self.result_store = build_result_store(self.settings)
        self.csv_exporter = EnjazCsvExporter()

        self.validator = PassportFeatureValidator(self.settings)
        self.face_detector = PassportFaceDetector(self.settings)
        self.extractor = build_extractor(self.settings)

    def close(self) -> None:
        self.loader.close()

    def process_source(self, source: str | Path) -> PassportProcessingResult:
        trace_id = uuid4().hex
        source_str = str(source)
        log = bind_logger(logging.getLogger(__name__), trace_id=trace_id, source=source_str)

        stored_original_uri: str | None = None
        stored_aligned_uri: str | None = None
        validation = ValidationResult(is_passport=False)
        face: FaceDetectionResult | None = None
        data: PassportData | None = None
        error_details: list[ProcessingError] = []

        log.info("pipeline_started")

        try:
            loaded = self.loader.load(source)
        except Exception as exc:
            self._append_error(
                error_details,
                code=ErrorCode.INPUT_LOAD_ERROR,
                stage="load",
                message=str(exc),
                retryable=False,
            )
            log.error("stage_failed", extra={"stage": "load", "error_code": ErrorCode.INPUT_LOAD_ERROR})
            return self._finalize_result(
                trace_id=trace_id,
                source=source_str,
                stored_original_uri=stored_original_uri,
                stored_aligned_uri=stored_aligned_uri,
                validation=validation,
                face=face,
                data=data,
                error_details=error_details,
                log=log,
            )

        try:
            stored_original_uri = self.binary_store.save(
                loaded.data,
                folder="originals",
                filename=loaded.filename,
                content_type=loaded.mime_type,
            )
        except Exception as exc:
            wrapped = StorageError(str(exc))
            self._append_error(
                error_details,
                code=wrapped.code,
                stage=wrapped.stage,
                message=wrapped.message,
                retryable=wrapped.retryable,
            )
            log.error("stage_failed", extra={"stage": wrapped.stage, "error_code": wrapped.code})

        try:
            match = self.validator.validate(loaded.bgr)
            validation = match.result
        except Exception as exc:
            self._append_error(
                error_details,
                code=ErrorCode.VALIDATION_ERROR,
                stage="validate",
                message=str(exc),
                retryable=False,
            )
            log.error("stage_failed", extra={"stage": "validate", "error_code": ErrorCode.VALIDATION_ERROR})
            return self._finalize_result(
                trace_id=trace_id,
                source=source_str,
                stored_original_uri=stored_original_uri,
                stored_aligned_uri=stored_aligned_uri,
                validation=validation,
                face=face,
                data=data,
                error_details=error_details,
                log=log,
            )

        if validation.is_passport and match.aligned_bgr is None:
            self._append_error(
                error_details,
                code=ErrorCode.ALIGNMENT_ERROR,
                stage="align",
                message="Passport validated but alignment failed; extraction skipped.",
                retryable=False,
            )
            log.error("stage_failed", extra={"stage": "align", "error_code": ErrorCode.ALIGNMENT_ERROR})

        if validation.is_passport and match.aligned_bgr is not None:
            try:
                aligned_bytes = encode_jpeg(match.aligned_bgr)

                stored_aligned_uri = self.binary_store.save(
                    aligned_bytes,
                    folder="aligned",
                    filename="aligned.jpg",
                    content_type="image/jpeg",
                )
            except Exception as exc:
                wrapped = StorageError(str(exc))
                self._append_error(
                    error_details,
                    code=wrapped.code,
                    stage=wrapped.stage,
                    message=wrapped.message,
                    retryable=wrapped.retryable,
                )
                log.error("stage_failed", extra={"stage": wrapped.stage, "error_code": wrapped.code})
                aligned_bytes = None

            try:
                face = self.face_detector.detect(
                    match.aligned_bgr,
                    match.homography_template_to_work,
                    match.work_to_original_scale,
                )
            except Exception as exc:
                wrapped = FaceDetectionError(str(exc))
                self._append_error(
                    error_details,
                    code=wrapped.code,
                    stage=wrapped.stage,
                    message=wrapped.message,
                    retryable=wrapped.retryable,
                )
                log.error("stage_failed", extra={"stage": wrapped.stage, "error_code": wrapped.code})

            if aligned_bytes is not None:
                try:
                    data = self.extractor.extract(aligned_bytes, "image/jpeg")
                except Exception as exc:
                    wrapped = ExtractionError(str(exc))
                    self._append_error(
                        error_details,
                        code=wrapped.code,
                        stage=wrapped.stage,
                        message=wrapped.message,
                        retryable=wrapped.retryable,
                    )
                    log.error(
                        "stage_failed",
                        extra={"stage": wrapped.stage, "error_code": wrapped.code},
                    )

        return self._finalize_result(
            trace_id=trace_id,
            source=source_str,
            stored_original_uri=stored_original_uri,
            stored_aligned_uri=stored_aligned_uri,
            validation=validation,
            face=face,
            data=data,
            error_details=error_details,
            log=log,
        )

    def process_sources(self, sources: Sequence[str | Path]) -> list[PassportProcessingResult]:
        return [self.process_source(source) for source in sources]

    def export_results_csv(
        self,
        results: Sequence[PassportProcessingResult],
        output_path: str | Path,
    ) -> None:
        self.csv_exporter.export(results, Path(output_path))

    def export_all_csv(self, output_path: str | Path) -> None:
        self.csv_exporter.export(self.result_store.fetch_all(), Path(output_path))

    @staticmethod
    def _append_error(
        errors: list[ProcessingError],
        *,
        code: ErrorCode,
        stage: str,
        message: str,
        retryable: bool,
    ) -> None:
        errors.append(
            ProcessingError(
                code=code,
                stage=stage,
                message=message,
                retryable=retryable,
            )
        )

    def _finalize_result(
        self,
        *,
        trace_id: str,
        source: str,
        stored_original_uri: str | None,
        stored_aligned_uri: str | None,
        validation: ValidationResult,
        face: FaceDetectionResult | None,
        data: PassportData | None,
        error_details: list[ProcessingError],
        log: logging.LoggerAdapter[logging.Logger],
    ) -> PassportProcessingResult:
        result = PassportProcessingResult(
            source=source,
            trace_id=trace_id,
            stored_original_uri=stored_original_uri,
            stored_aligned_uri=stored_aligned_uri,
            validation=validation,
            face=face,
            data=data,
            error_details=error_details,
        )

        try:
            self.result_store.save(result)
        except Exception as exc:
            self._append_error(
                result.error_details,
                code=ErrorCode.STORAGE_ERROR,
                stage="store",
                message=f"Result-store save failed: {exc}",
                retryable=True,
            )
            log.error("result_store_save_failed", extra={"stage": "store", "error_code": "STORAGE_ERROR"})

        log.info("pipeline_finished")
        return result
