from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from passport_core.config import Settings
from passport_core.errors import ErrorCode, ExtractionError, StorageError
from passport_core.io import EnjazCsvExporter, build_binary_store, build_result_store
from passport_core.log import bind_logger
from passport_core.models import (
    FaceCropResult,
    FaceDetectionResult,
    PassportData,
    PassportProcessingResult,
    ProcessingError,
    ValidationResult,
)
from passport_core.workflow import PassportWorkflow, PassportWorkflowResult


def to_processing_result(
    workflow_result: PassportWorkflowResult,
    *,
    trace_id: str,
    passport_image_uri: str | None = None,
    face_crop_uri: str | None = None,
    error_details: list[ProcessingError] | None = None,
) -> PassportProcessingResult:
    return PassportProcessingResult(
        source=workflow_result.source,
        trace_id=trace_id,
        passport_image_uri=passport_image_uri,
        face_crop_uri=face_crop_uri,
        validation=workflow_result.validation,
        face=workflow_result.face,
        data=workflow_result.data,
        error_details=error_details or [],
    )


class PassportCoreService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

        self.binary_store = build_binary_store(self.settings)
        self.result_store = build_result_store(self.settings)
        self.csv_exporter = EnjazCsvExporter()
        self.workflow = PassportWorkflow(settings=self.settings)

    def close(self) -> None:
        self.workflow.close()

    def process_source(self, source: str | Path) -> PassportProcessingResult:
        trace_id = uuid4().hex
        source_str = str(source)
        log = bind_logger(logging.getLogger(__name__), trace_id=trace_id, source=source_str)

        passport_image_uri: str | None = None
        face_crop_uri: str | None = None
        validation = ValidationResult(is_passport=False)
        face: FaceDetectionResult | None = None
        data: PassportData | None = None
        error_details: list[ProcessingError] = []
        workflow_result: PassportWorkflowResult | None = None

        log.info("pipeline_started")

        try:
            loaded = self.workflow.load_source(source)
        except Exception as exc:
            self._append_error(
                error_details,
                code=ErrorCode.INPUT_LOAD_ERROR,
                stage="load",
                message=str(exc),
                retryable=False,
            )
            log.error(
                "stage_failed",
                extra={"stage": "load", "error_code": ErrorCode.INPUT_LOAD_ERROR},
            )
            return self._finalize_result(
                workflow_result=workflow_result,
                trace_id=trace_id,
                source=source_str,
                passport_image_uri=passport_image_uri,
                face_crop_uri=face_crop_uri,
                validation=validation,
                face=face,
                data=data,
                error_details=error_details,
                log=log,
            )

        try:
            passport_image_uri = self.binary_store.save(
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
            workflow_result = self.workflow.prepare_loaded(loaded)
            validation = workflow_result.validation
            face = workflow_result.face
            crop = workflow_result.face_crop
        except Exception as exc:
            self._append_error(
                error_details,
                code=ErrorCode.INTERNAL_ERROR,
                stage="prepare",
                message=str(exc),
                retryable=False,
            )
            log.error(
                "stage_failed",
                extra={"stage": "prepare", "error_code": ErrorCode.INTERNAL_ERROR},
            )
            return self._finalize_result(
                workflow_result=workflow_result,
                trace_id=trace_id,
                source=source_str,
                passport_image_uri=passport_image_uri,
                face_crop_uri=face_crop_uri,
                validation=validation,
                face=face,
                data=data,
                error_details=error_details,
                log=log,
            )

        if validation.is_passport:
            if crop is not None:
                try:
                    extraction_input = workflow_result.processed_loaded or loaded
                    data = self.workflow.extract_data(extraction_input)
                    workflow_result.data = data
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
                try:
                    face_crop_uri = self.binary_store.save(
                        crop.jpeg_bytes,
                        folder="faces",
                        filename=f"{Path(source_str).stem}_face.jpg",
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
                    log.error(
                        "stage_failed",
                        extra={"stage": wrapped.stage, "error_code": wrapped.code},
                    )
            else:
                self._append_error(
                    error_details,
                    code=ErrorCode.FACE_DETECTION_ERROR,
                    stage="face_detect",
                    message="No face crop could be produced from the passport image.",
                    retryable=False,
                )

        return self._finalize_result(
            workflow_result=workflow_result,
            trace_id=trace_id,
            source=source_str,
            passport_image_uri=passport_image_uri,
            face_crop_uri=face_crop_uri,
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

    def crop_face(self, source: str | Path) -> FaceCropResult | None:
        loaded = self.workflow.load_source(source)
        result = self.workflow.prepare_loaded(loaded)
        if not result.validation.is_passport or result.face_crop is None:
            return None

        stored_uri = self.binary_store.save(
            result.face_crop.jpeg_bytes,
            folder="faces",
            filename=f"{Path(str(source)).stem}_face.jpg",
            content_type="image/jpeg",
        )
        result.face_crop.stored_uri = stored_uri
        return result.face_crop

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
        workflow_result: PassportWorkflowResult | None = None,
        trace_id: str,
        source: str,
        passport_image_uri: str | None,
        face_crop_uri: str | None,
        validation: ValidationResult,
        face: FaceDetectionResult | None,
        data: PassportData | None,
        error_details: list[ProcessingError],
        log: logging.LoggerAdapter[logging.Logger],
    ) -> PassportProcessingResult:
        if workflow_result is None:
            result = PassportProcessingResult(
                source=source,
                trace_id=trace_id,
                passport_image_uri=passport_image_uri,
                face_crop_uri=face_crop_uri,
                validation=validation,
                face=face,
                data=data,
                error_details=error_details,
            )
        else:
            result = to_processing_result(
                workflow_result,
                trace_id=trace_id,
                passport_image_uri=passport_image_uri,
                face_crop_uri=face_crop_uri,
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
            log.error(
                "result_store_save_failed",
                extra={"stage": "store", "error_code": "STORAGE_ERROR"},
            )

        log.info("pipeline_finished")
        return result
