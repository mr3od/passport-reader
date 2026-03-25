from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

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


def test_tracked_processing_result_exposes_legacy_v1_names():
    result = make_tracked_result(
        {
            "PassportNumber": "12345678",
            "SurnameAr": "الهاشمي",
            "GivenNamesAr": "أحمد علي",
            "SurnameEn": "ALHASHMI",
            "GivenNamesEn": "AHMAD ALI",
        }
    )

    data = result.extracted_data

    assert data is not None
    assert data.full_name_ar == "أحمد علي الهاشمي"
    assert data.full_name_en == "AHMAD ALI ALHASHMI"
    assert result.image_bytes == b"passport"
    assert result.face_crop_bytes == b"face"


def test_tracked_processing_result_exposes_v2_tokenized_names():
    result = make_tracked_result(
        {
            "PassportNumber": "87654321",
            "SurnameAr": "العكبري",
            "GivenNameTokensAr": ["عبدالله", "مرشد", "حسن"],
            "SurnameEn": "AL-AKBARI",
            "GivenNameTokensEn": ["ABDULLAH", "MURSHED", "HASAN"],
        }
    )

    data = result.extracted_data

    assert data is not None
    assert data.given_names_ar == "عبدالله مرشد حسن"
    assert data.given_names_en == "ABDULLAH MURSHED HASAN"
    assert data.full_name_ar == "عبدالله مرشد حسن العكبري"
    assert data.full_name_en == "ABDULLAH MURSHED HASAN AL-AKBARI"


def make_tracked_result(extracted_data: dict[str, object]) -> TrackedProcessingResult:
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
        has_face=True,
        is_complete=True,
        passport_number="12345678",
        passport_image_uri="/tmp/original.jpg",
        face_crop_uri="/tmp/face.jpg",
        core_result_json=None,
        error_code=None,
        completed_at=datetime(2026, 3, 13, 10, 1, tzinfo=UTC),
        masar_status=None,
        masar_mutamer_id=None,
        masar_scan_result_json=None,
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
        workflow_result=SimpleNamespace(
            image_bytes=b"passport",
            face_crop_bytes=b"face",
            data=extracted_data,
        ),
        processing_result=processing_result,
    )
