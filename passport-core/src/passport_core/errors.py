from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INPUT_LOAD_ERROR = "INPUT_LOAD_ERROR"
    STORAGE_ERROR = "STORAGE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    ALIGNMENT_ERROR = "ALIGNMENT_ERROR"
    FACE_DETECTION_ERROR = "FACE_DETECTION_ERROR"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class PassportCoreError(Exception):
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    stage: str = "unknown"
    retryable: bool = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InputLoadError(PassportCoreError):
    code = ErrorCode.INPUT_LOAD_ERROR
    stage = "load"


class StorageError(PassportCoreError):
    code = ErrorCode.STORAGE_ERROR
    stage = "store"


class ValidationError(PassportCoreError):
    code = ErrorCode.VALIDATION_ERROR
    stage = "validate"


class AlignmentError(PassportCoreError):
    code = ErrorCode.ALIGNMENT_ERROR
    stage = "align"


class FaceDetectionError(PassportCoreError):
    code = ErrorCode.FACE_DETECTION_ERROR
    stage = "face_detect"


class ExtractionError(PassportCoreError):
    code = ErrorCode.EXTRACTION_ERROR
    stage = "extract"
    retryable = True
