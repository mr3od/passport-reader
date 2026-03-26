from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from passport_platform import (
    IssuedTempToken,
    MonthlyUsageReport,
    PlanName,
    QuotaDecision,
    RecentUploadRecord,
    TrackedProcessingResult,
    UserUsageReport,
)
from passport_platform.enums import ChannelName, ExternalProvider, UploadStatus, UserStatus
from passport_platform.models.upload import ProcessingResult, Upload
from passport_platform.models.user import User

from passport_telegram.messages import (
    admin_help_text,
    admin_only_text,
    format_failure_text,
    format_monthly_usage_report,
    format_recent_uploads,
    format_success_text,
    format_user_plan_text,
    format_user_usage_report,
    help_text,
    processing_error_text,
    quota_exceeded_text,
    temp_token_text,
    user_blocked_text,
    user_not_found_text,
    user_plan_updated_text,
    user_status_updated_text,
    welcome_text,
)


def test_format_failure_for_non_passport():
    result = make_tracked_result(is_passport=False, extracted_data=None)

    text = format_failure_text(result, position=1, total=1)

    assert "تعذر التحقق" in text


def test_format_success_includes_key_fields():
    result = make_tracked_result(
        is_passport=True,
        extracted_data={
            "PassportNumber": "A123",
            "SurnameAr": "الهاشمي",
            "GivenNameTokensAr": ["أحمد", "علي"],
            "SurnameEn": "ALHASHMI",
            "GivenNameTokensEn": ["AHMAD", "ALI"],
            "DateOfBirth": "01/01/1990",
            "PlaceOfBirthAr": "صنعاء",
            "ProfessionAr": "طالب",
            "IssuingAuthorityAr": "القاهرة",
        },
    )

    text = format_success_text(result, position=1, total=1)

    assert "الاسم الكامل بالعربية: `أحمد علي الهاشمي`" in text
    assert "الاسم الكامل بالإنجليزية: `AHMAD ALI ALHASHMI`" in text
    assert "رقم الجواز: `A123`" in text
    assert "مكان الميلاد: `صنعاء`" in text
    assert "نسخ سريع" in text


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
            reason="لا يمكن رفع المزيد من الجوازات هذا الشهر",
        )
    )

    assert "0" in text
    assert "2" in text
    assert "@mr3od" in text
    assert "@naaokun" in text


def test_user_blocked_text_mentions_account_stop():
    assert "إيقاف" in user_blocked_text()
    assert "@mr3od" in user_blocked_text()


def test_help_and_welcome_texts_include_support_contacts():
    assert "/account" in help_text()
    assert "/usage" in help_text()
    assert "/plan" in help_text()
    assert "/token" in help_text()
    assert "@mr3od" in help_text()
    assert "@naaokun" in help_text()
    assert "/account" in welcome_text()
    assert "/usage" in welcome_text()
    assert "/plan" in welcome_text()
    assert "/token" in welcome_text()
    assert "@mr3od" in welcome_text()


def test_processing_error_text_includes_support_contacts():
    text = processing_error_text()

    assert "@mr3od" in text
    assert "@naaokun" in text


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


def test_format_user_plan_text_includes_plan_and_status():
    user = User(
        id=1,
        external_provider="telegram",  # type: ignore[arg-type]
        external_user_id="12345",
        display_name="Agency A",
        plan=PlanName.PRO,
        status=UserStatus.ACTIVE,
        created_at=None,  # type: ignore[arg-type]
    )

    text = format_user_plan_text(user)

    assert "Agency A" in text
    assert "pro" in text
    assert "active" in text


def test_temp_token_text_includes_token_and_expiry():
    text = temp_token_text(
        IssuedTempToken(
            token="abc123",
            expires_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
            record=None,  # type: ignore[arg-type]
        )
    )

    assert "abc123" in text
    assert "2026-03-13 12:00 UTC" in text
    assert "مرة واحدة" in text


def make_tracked_result(
    *,
    is_passport: bool,
    extracted_data: dict[str, object] | None,
    review_status: str = "auto",
    confidence_overall: float | None = 0.91,
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
        status=UploadStatus.PROCESSED if is_passport else UploadStatus.FAILED,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
    )
    processing_result = ProcessingResult(
        id=1,
        upload_id=upload.id,
        is_passport=is_passport,
        is_complete=is_passport and extracted_data is not None,
        review_status=review_status,
        reviewed_by_user_id=None,
        reviewed_at=None,
        passport_number=(
            extracted_data.get("PassportNumber") if isinstance(extracted_data, dict) else None
        ),
        passport_image_uri="/tmp/original.jpg",
        confidence_overall=confidence_overall,
        extraction_result_json=None,
        error_code=None,
        completed_at=datetime(2026, 3, 13, 10, 1, tzinfo=UTC),
    )
    extraction_result = (
        SimpleNamespace(data=extracted_data, warnings=[]) if extracted_data is not None else None
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
