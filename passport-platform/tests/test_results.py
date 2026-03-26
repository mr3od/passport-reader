from __future__ import annotations

from datetime import UTC, datetime

from passport_core.extraction.models import (
    Confidence,
    ExtractionResult,
    PassportFields,
)

from passport_platform.enums import (
    ChannelName,
    ExternalProvider,
    PlanName,
    UploadStatus,
    UserStatus,
)
from passport_platform.models.upload import ProcessingResult, Upload
from passport_platform.models.user import User
from passport_platform.schemas.results import QuotaDecision, TrackedProcessingResult


def test_tracked_processing_result_exposes_v2_tokenized_names() -> None:
    result = make_tracked_result(
        ExtractionResult(
            data=PassportFields(
                PassportNumber="87654321",
                SurnameAr="العكبري",
                GivenNameTokensAr=["عبدالله", "مرشد", "حسن"],
                SurnameEn="AL-AKBARI",
                GivenNameTokensEn=["ABDULLAH", "MURSHED", "HASAN"],
            ),
            confidence=Confidence(overall=0.91),
            warnings=[],
        )
    )

    data = result.extracted_data

    assert data is not None
    assert data.given_names_ar == "عبدالله مرشد حسن"
    assert data.given_names_en == "ABDULLAH MURSHED HASAN"
    assert data.full_name_ar == "عبدالله مرشد حسن العكبري"
    assert data.full_name_en == "ABDULLAH MURSHED HASAN AL-AKBARI"
    assert result.confidence_overall == 0.91
    assert result.review_status == "auto"


def test_tracked_processing_result_exposes_warning_list() -> None:
    result = make_tracked_result(
        ExtractionResult(
            data=PassportFields(PassportNumber="12345678"),
            confidence=Confidence(overall=0.62),
            warnings=["Given name tokens: Arabic=4 vs English=3"],
        ),
        review_status="needs_review",
    )

    assert result.warnings == ["Given name tokens: Arabic=4 vs English=3"]
    assert result.review_status == "needs_review"


def make_tracked_result(
    extraction_result: ExtractionResult,
    *,
    review_status: str = "auto",
) -> TrackedProcessingResult:
    user = User(
        id=1,
        external_provider=ExternalProvider.TELEGRAM,
        external_user_id="12345",
        display_name="Agency A",
        plan=PlanName.BASIC,
        status=UserStatus.ACTIVE,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
    )
    upload = Upload(
        id=1,
        user_id=user.id,
        channel=ChannelName.TELEGRAM,
        external_message_id="1",
        external_file_id="file-1",
        filename="passport.jpg",
        mime_type="image/jpeg",
        source_ref="telegram://1",
        status=UploadStatus.PROCESSED,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
    )
    processing_result = ProcessingResult(
        id=1,
        upload_id=upload.id,
        is_passport=True,
        is_complete=True,
        review_status=review_status,
        reviewed_by_user_id=None,
        reviewed_at=None,
        passport_number=extraction_result.data.PassportNumber,
        passport_image_uri="/tmp/original.jpg",
        confidence_overall=extraction_result.confidence.overall,
        extraction_result_json=extraction_result.model_dump_json(),
        error_code=None,
        completed_at=datetime(2026, 3, 13, 10, 1, tzinfo=UTC),
    )

    return TrackedProcessingResult(
        user=user,
        upload=upload,
        quota_decision=QuotaDecision(
            allowed=True,
            plan=PlanName.BASIC,
            monthly_upload_limit=300,
            monthly_uploads_used=0,
            monthly_success_limit=300,
            monthly_successes_used=0,
            remaining_uploads=300,
            remaining_successes=300,
            max_batch_size=10,
        ),
        extraction_result=extraction_result,
        processing_result=processing_result,
    )
