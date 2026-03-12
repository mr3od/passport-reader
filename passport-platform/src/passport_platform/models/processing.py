from __future__ import annotations

from dataclasses import dataclass

from passport_platform.models.upload import ProcessingResult, Upload


@dataclass(slots=True)
class RecordedProcessing:
    upload: Upload
    processing_result: ProcessingResult
