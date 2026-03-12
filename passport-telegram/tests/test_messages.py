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
from passport_platform import (
    MonthlyUsageReport,
    PlanName,
    QuotaDecision,
    RecentUploadRecord,
    UserUsageReport,
)
from passport_platform.enums import UploadStatus, UserStatus
from passport_platform.models.user import User

from passport_telegram.messages import (
    admin_help_text,
    admin_only_text,
    format_failure_text,
    format_monthly_usage_report,
    format_recent_uploads,
    format_success_text,
    format_user_usage_report,
    quota_exceeded_text,
    user_blocked_text,
    user_not_found_text,
    user_plan_updated_text,
    user_status_updated_text,
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


def test_admin_texts_cover_commands_and_restrictions():
    assert "/stats" in admin_help_text()
    assert "مخصص للمسؤول" in admin_only_text()


def test_reporting_messages_include_summary_fields():
    user = User(
        id=1,
        external_provider="telegram",  # type: ignore[arg-type]
        external_user_id="12345",
        display_name="Agency A",
        plan=PlanName.BASIC,
        status=UserStatus.ACTIVE,
        created_at=None,  # type: ignore[arg-type]
    )
    usage_text = format_user_usage_report(
        UserUsageReport(
            user=user,
            quota_decision=QuotaDecision(
                allowed=True,
                plan=PlanName.BASIC,
                monthly_upload_limit=300,
                monthly_uploads_used=2,
                monthly_success_limit=300,
                monthly_successes_used=1,
                remaining_uploads=298,
                remaining_successes=299,
                max_batch_size=10,
            ),
            period_start=None,  # type: ignore[arg-type]
            period_end=None,  # type: ignore[arg-type]
            upload_count=2,
            success_count=1,
            failure_count=1,
        )
    )
    monthly_text = format_monthly_usage_report(
        MonthlyUsageReport(
            period_start=None,  # type: ignore[arg-type]
            period_end=None,  # type: ignore[arg-type]
            total_users=2,
            active_users=1,
            blocked_users=1,
            total_uploads=3,
            total_successes=2,
            total_failures=1,
        )
    )
    recent_text = format_recent_uploads(
        [
            RecentUploadRecord(
                upload_id=1,
                user_id=1,
                external_provider="telegram",
                external_user_id="12345",
                display_name="Agency A",
                plan=PlanName.BASIC,
                user_status=UserStatus.ACTIVE,
                filename="passport.jpg",
                source_ref="telegram://1",
                upload_status=UploadStatus.PROCESSED,
                passport_number="A123",
                error_code=None,
                created_at=None,  # type: ignore[arg-type]
                completed_at=None,
            )
        ]
    )

    assert "Agency A" in usage_text
    assert "إجمالي المستخدمين: 2" in monthly_text
    assert "passport.jpg" in recent_text


def test_admin_user_update_texts_include_identifier():
    user = User(
        id=1,
        external_provider="telegram",  # type: ignore[arg-type]
        external_user_id="12345",
        display_name=None,
        plan=PlanName.PRO,
        status=UserStatus.BLOCKED,
        created_at=None,  # type: ignore[arg-type]
    )

    assert "12345" in user_plan_updated_text(user)
    assert "12345" in user_status_updated_text(user)
    assert "999" in user_not_found_text("999")
