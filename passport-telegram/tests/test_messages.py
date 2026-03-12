from __future__ import annotations

from passport_core import (
    BoundingBox,
    FaceCropResult,
    FaceDetectionResult,
    LoadedImage,
    PassportData,
    PassportWorkflowResult,
    ValidationResult,
)
from passport_platform import PlanName, QuotaDecision

from passport_telegram.messages import (
    format_failure_text,
    format_success_text,
    quota_exceeded_text,
    user_blocked_text,
)


def test_format_failure_for_non_passport():
    result = PassportWorkflowResult(
        loaded=LoadedImage(
            source="telegram://1",
            data=b"raw",
            mime_type="image/jpeg",
            filename="x.jpg",
            bgr=None,  # type: ignore[arg-type]
        ),
        validation=ValidationResult(is_passport=False),
    )

    text = format_failure_text(result, position=1, total=1)

    assert "تعذر التحقق" in text


def test_format_success_includes_key_fields():
    result = PassportWorkflowResult(
        loaded=LoadedImage(
            source="telegram://1",
            data=b"raw",
            mime_type="image/jpeg",
            filename="x.jpg",
            bgr=None,  # type: ignore[arg-type]
        ),
        validation=ValidationResult(is_passport=True),
        face=FaceDetectionResult(
            bbox_original=BoundingBox(x=1, y=2, width=3, height=4, score=0.9)
        ),
        face_crop=FaceCropResult(
            bbox_original=BoundingBox(x=1, y=2, width=3, height=4, score=0.9),
            width=3,
            height=4,
            jpeg_bytes=b"face",
        ),
        data=PassportData(
            PassportNumber="A123",
            SurnameAr="الهاشمي",
            GivenNamesAr="أحمد علي",
            SurnameEn="ALHASHMI",
            GivenNamesEn="AHMAD ALI",
            DateOfBirth="01/01/1990",
        ),
    )

    text = format_success_text(result, position=1, total=1)

    assert "رقم الجواز: A123" in text
    assert "أحمد علي الهاشمي" in text
    assert "AHMAD ALI ALHASHMI" in text


def test_quota_exceeded_text_includes_remaining_limits():
    text = quota_exceeded_text(
        QuotaDecision(
            allowed=False,
            plan=PlanName.FREE,
            monthly_upload_limit=20,
            monthly_uploads_used=20,
            monthly_success_limit=20,
            monthly_successes_used=18,
            remaining_uploads=0,
            remaining_successes=2,
            max_batch_size=2,
            reason="monthly upload quota reached",
        )
    )

    assert "0" in text
    assert "2" in text


def test_user_blocked_text_mentions_account_stop():
    assert "إيقاف" in user_blocked_text()
