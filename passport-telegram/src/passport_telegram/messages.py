from __future__ import annotations

from passport_core import PassportWorkflowResult
from passport_platform import MonthlyUsageReport, QuotaDecision, RecentUploadRecord, UserUsageReport
from passport_platform.models.user import User


def welcome_text() -> str:
    return (
        "أهلًا بك في بوت رفع وتدقيق الجوازات.\n\n"
        "أرسل صورة جواز واحدة أو عدة صور، وسأقوم بالتحقق من الجواز، قص صورة الوجه، "
        "واستخراج بيانات الجواز لكل صورة."
    )


def help_text() -> str:
    return (
        "طريقة الاستخدام:\n"
        "1. أرسل صورة الجواز كصورة أو كملف.\n"
        "2. يمكنك إرسال أكثر من صورة في دفعة واحدة.\n"
        "3. ستصلك النتيجة لكل صورة بشكل مستقل.\n\n"
        "الملفات المدعومة: JPG, JPEG, PNG, WEBP, TIF, TIFF"
    )


def admin_help_text() -> str:
    return (
        "أوامر المسؤول:\n"
        "/stats - ملخص الاستخدام الشهري\n"
        "/recent [عدد] - آخر العمليات\n"
        "/usage <telegram_user_id> - استخدام مستخدم محدد\n"
        "/setplan <telegram_user_id> <free|basic|pro> - تغيير الخطة\n"
        "/block <telegram_user_id> - حظر مستخدم\n"
        "/unblock <telegram_user_id> - فك الحظر عن مستخدم"
    )


def batch_started_text(total: int) -> str:
    if total == 1:
        return "جارٍ معالجة الصورة الآن."
    return f"جارٍ معالجة {total} صور."


def format_failure_text(result: PassportWorkflowResult, *, position: int, total: int) -> str:
    prefix = f"الصورة {position} من {total}\n" if total > 1 else ""

    if not result.validation.is_passport:
        return prefix + "تعذر التحقق من أن الصورة تحتوي على جواز صالح للمعالجة."

    if not result.has_face_crop:
        return prefix + "تم التحقق من الجواز، لكن تعذر استخراج صورة الوجه."

    return prefix + "تعذر إكمال معالجة الصورة."


def format_success_text(result: PassportWorkflowResult, *, position: int, total: int) -> str:
    prefix = f"الصورة {position} من {total}\n" if total > 1 else ""
    data = result.data
    if data is None:
        return prefix + "تعذر استخراج البيانات."

    lines = [
        prefix + "تمت معالجة الجواز بنجاح.",
        f"رقم الجواز: {_value(data.PassportNumber)}",
        f"الاسم بالعربية: {_join_values(data.GivenNamesAr, data.SurnameAr)}",
        f"الاسم بالإنجليزية: {_join_values(data.GivenNamesEn, data.SurnameEn)}",
        f"الجنسية: {_value(data.CountryCode)}",
        f"تاريخ الميلاد: {_value(data.DateOfBirth)}",
        f"الجنس: {_value(data.Sex)}",
        f"مكان الميلاد: {_join_values(data.PlaceOfBirthAr, data.PlaceOfBirthEn, separator=' | ')}",
        f"المهنة: {_join_values(data.ProfessionAr, data.ProfessionEn, separator=' | ')}",
        (
            "جهة الإصدار: "
            + _join_values(data.IssuingAuthorityAr, data.IssuingAuthorityEn, separator=" | ")
        ),
        f"تاريخ الإصدار: {_value(data.DateOfIssue)}",
        f"تاريخ الانتهاء: {_value(data.DateOfExpiry)}",
    ]
    return "\n".join(line for line in lines if line.strip())


def unsupported_file_text() -> str:
    return "الملف المرسل ليس صورة جواز مدعومة. أرسل صورة أو ملف صورة واضح."


def unauthorized_text() -> str:
    return "هذا البوت غير مفعّل لهذه المحادثة."


def admin_only_text() -> str:
    return "هذا الأمر مخصص للمسؤول."


def processing_error_text() -> str:
    return "حدث خطأ أثناء المعالجة. حاول مرة أخرى بصورة أوضح."


def quota_exceeded_text(decision: QuotaDecision) -> str:
    return (
        "تم استهلاك الحد المسموح لخطة الاستخدام الحالية.\n"
        f"المتبقي من رفع الصور هذا الشهر: {decision.remaining_uploads}\n"
        f"المتبقي من المعالجات الناجحة هذا الشهر: {decision.remaining_successes}"
    )


def user_blocked_text() -> str:
    return "تم إيقاف هذا الحساب عن استخدام الخدمة. راجع المسؤول."


def admin_usage_help_text() -> str:
    return "الاستخدام: /usage <telegram_user_id>"


def admin_setplan_help_text() -> str:
    return "الاستخدام: /setplan <telegram_user_id> <free|basic|pro>"


def admin_status_help_text(command_name: str) -> str:
    return f"الاستخدام: /{command_name} <telegram_user_id>"


def user_not_found_text(external_user_id: str) -> str:
    return f"تعذر العثور على المستخدم: {external_user_id}"


def format_monthly_usage_report(report: MonthlyUsageReport) -> str:
    return (
        "ملخص الاستخدام الشهري:\n"
        f"إجمالي المستخدمين: {report.total_users}\n"
        f"المستخدمون النشطون: {report.active_users}\n"
        f"المستخدمون المحظورون: {report.blocked_users}\n"
        f"إجمالي الصور المرفوعة: {report.total_uploads}\n"
        f"المعالجات الناجحة: {report.total_successes}\n"
        f"المعالجات الفاشلة: {report.total_failures}"
    )


def format_user_usage_report(report: UserUsageReport) -> str:
    user = report.user
    return (
        f"المستخدم: {_user_label(user)}\n"
        f"معرف تيليجرام: {user.external_user_id}\n"
        f"خطة الاستخدام: {user.plan.value}\n"
        f"حالة الحساب: {user.status.value}\n"
        f"عدد الصور هذا الشهر: {report.upload_count}\n"
        f"المعالجات الناجحة: {report.success_count}\n"
        f"المعالجات الفاشلة: {report.failure_count}\n"
        f"المتبقي من رفع الصور: {report.quota_decision.remaining_uploads}\n"
        f"المتبقي من المعالجات الناجحة: {report.quota_decision.remaining_successes}"
    )


def format_recent_uploads(records: list[RecentUploadRecord]) -> str:
    if not records:
        return "لا توجد عمليات حديثة."
    lines = ["آخر العمليات:"]
    for record in records:
        lines.append(
            f"- {record.external_user_id} | {record.filename} | "
            f"{record.upload_status.value} | "
            f"{record.passport_number or record.error_code or '-'}"
        )
    return "\n".join(lines)


def user_plan_updated_text(user: User) -> str:
    return f"تم تحديث خطة المستخدم {user.external_user_id} إلى {user.plan.value}."


def user_status_updated_text(user: User) -> str:
    return f"تم تحديث حالة المستخدم {user.external_user_id} إلى {user.status.value}."


def _value(value: str | None) -> str:
    return value or "-"


def _join_values(*values: str | None, separator: str = " ") -> str:
    clean = [value.strip() for value in values if value and value.strip()]
    return separator.join(clean) if clean else "-"


def _user_label(user: User) -> str:
    return user.display_name or user.external_user_id
