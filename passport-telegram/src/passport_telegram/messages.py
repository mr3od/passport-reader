from __future__ import annotations

from datetime import UTC

from passport_platform import (
    IssuedTempToken,
    MonthlyUsageReport,
    QuotaDecision,
    RecentUploadRecord,
    TrackedProcessingResult,
    UserUsageReport,
)
from passport_platform.models.user import User
from passport_platform.schemas.results import UserRecord

SUPPORT_CONTACT_TEXT = "للاستفسارات أو طلب تغيير الخطة، تواصل مع @mr3od أو @naaokun."


def welcome_text() -> str:
    return (
        "أهلًا بك في بوت رفع وتدقيق الجوازات.\n\n"
        "أرسل صورة جواز واحدة أو عدة صور، وسأقوم بالتحقق من الجواز، قص صورة الوجه، "
        "واستخراج البيانات لكل صورة بشكل مستقل.\n\n"
        "أوامر المستخدم:\n"
        "/account - عرض الخطة والاستخدام الحالي\n"
        "/usage - عرض تفاصيل الاستخدام الشهري\n"
        "/plan - عرض الخطة الحالية وحالة الحساب\n"
        "/token - إصدار رمز مؤقت لتسجيل الدخول في الإضافة\n"
        "/masar - عرض الجوازات المعلقة أو الفاشلة في مسار\n\n"
        f"{SUPPORT_CONTACT_TEXT}"
    )


def help_text() -> str:
    return (
        "طريقة الاستخدام:\n"
        "1. أرسل صورة الجواز كصورة أو كملف.\n"
        "2. تأكد من أن الصورة واضحة وتُظهر كامل صفحة الجواز.\n"
        "3. يمكنك إرسال أكثر من صورة في دفعة واحدة.\n"
        "4. ستصلك النتيجة لكل صورة بشكل مستقل، مع صورة الوجه والبيانات المستخرجة.\n\n"
        "أوامر المستخدم:\n"
        "/account - عرض الخطة والاستخدام الحالي\n"
        "/usage - عرض تفاصيل الاستخدام الشهري\n"
        "/plan - عرض الخطة الحالية وحالة الحساب\n"
        "/token - إصدار رمز مؤقت لتسجيل الدخول في الإضافة\n"
        "/masar - عرض الجوازات المعلقة أو الفاشلة في مسار\n\n"
        "الملفات المدعومة: JPG, JPEG, PNG, WEBP, TIF, TIFF\n\n"
        f"{SUPPORT_CONTACT_TEXT}"
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
        return "تم استلام الصورة، وجارٍ معالجتها الآن."
    return f"تم استلام {total} صور، وجارٍ معالجتها الآن."


def batch_limit_exceeded_text(*, total: int, limit: int) -> str:
    return (
        f"عدد الصور المرسلة ({total}) يتجاوز الحد المسموح في الدفعة الواحدة ({limit}).\n"
        "قسّم الصور إلى دفعات أصغر ثم أعد الإرسال."
    )


def format_failure_text(result: TrackedProcessingResult, *, position: int, total: int) -> str:
    prefix = f"الصورة {position} من {total}\n" if total > 1 else ""

    if not result.is_passport:
        return (
            prefix + "تعذر التحقق من أن الصورة تخص جوازًا صالحًا للمعالجة. "
            "تأكد من وضوح الصورة وإظهار كامل صفحة الجواز."
        )

    if not result.has_face_crop:
        return (
            prefix + "تم التحقق من الجواز، لكن تعذر استخراج صورة الوجه. "
            "يُفضّل إعادة الإرسال بصورة أوضح وأعلى دقة."
        )

    return prefix + "تعذر إكمال معالجة الصورة الحالية. يُرجى إعادة المحاولة بصورة أوضح."


def format_success_text(result: TrackedProcessingResult, *, position: int, total: int) -> str:
    prefix = f"الصورة {position} من {total}\n" if total > 1 else ""
    data = result.extracted_data
    if data is None:
        return prefix + "تعذر استخراج البيانات من الصورة الحالية."

    lines = [
        prefix + "تمت معالجة الجواز بنجاح.",
        "نسخ سريع:",
        f"الاسم الكامل بالعربية: {_code(data.full_name_ar)}",
        f"الاسم الكامل بالإنجليزية: {_code(data.full_name_en)}",
        f"رقم الجواز: {_code(data.passport_number)}",
        f"الجنسية: {_code(data.country_code)}",
        f"تاريخ الميلاد: {_code(data.date_of_birth)}",
        f"الجنس: {_code(data.sex)}",
        f"مكان الميلاد: {_code(_first_value(data.place_of_birth_ar, data.place_of_birth_en))}",
        f"المهنة: {_code(_first_value(data.profession_ar, data.profession_en))}",
        f"جهة الإصدار: {_code(_first_value(data.issuing_authority_ar, data.issuing_authority_en))}",
        f"تاريخ الإصدار: {_code(data.date_of_issue)}",
        f"تاريخ الانتهاء: {_code(data.date_of_expiry)}",
    ]
    return "\n".join(line for line in lines if line.strip())


def unsupported_file_text() -> str:
    return "الملف المرسل ليس صورة جواز مدعومة. أرسل صورة واضحة للجواز كصورة أو كملف صورة."


def unauthorized_text() -> str:
    return "هذا البوت غير مفعّل لهذه المحادثة."


def admin_only_text() -> str:
    return "هذا الأمر مخصص للمسؤول."


def processing_error_text() -> str:
    return f"حدث خطأ أثناء المعالجة. حاول مرة أخرى بصورة أوضح. {SUPPORT_CONTACT_TEXT}"


def quota_exceeded_text(decision: QuotaDecision) -> str:
    return (
        "تم استهلاك الحد المسموح لخطة الاستخدام الحالية.\n"
        f"المتبقي من رفع الصور هذا الشهر: {decision.remaining_uploads}\n"
        f"المتبقي من المعالجات الناجحة هذا الشهر: {decision.remaining_successes}\n\n"
        f"{SUPPORT_CONTACT_TEXT}"
    )


def user_blocked_text() -> str:
    return f"تم إيقاف هذا الحساب عن استخدام الخدمة مؤقتًا. {SUPPORT_CONTACT_TEXT}"


def admin_usage_help_text() -> str:
    return "الاستخدام: /usage <telegram_user_id>"


def admin_setplan_help_text() -> str:
    return "الاستخدام: /setplan <telegram_user_id> <free|basic|pro>"


def admin_status_help_text(command_name: str) -> str:
    return f"الاستخدام: /{command_name} <telegram_user_id>"


def user_not_found_text(external_user_id: str) -> str:
    return f"تعذر العثور على المستخدم: {external_user_id}"


def temp_token_text(issued: IssuedTempToken) -> str:
    expires_at = issued.expires_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "تم إصدار رمز تسجيل دخول مؤقت للإضافة.\n"
        f"الرمز: `{issued.token}`\n"
        f"ينتهي في: {expires_at}\n"
        "هذا الرمز صالح للاستخدام مرة واحدة فقط.\n"
        "الصقه في شاشة تسجيل الدخول داخل الإضافة."
    )


def format_masar_status_text(records: list[UserRecord]) -> str:
    if not records:
        return "جميع الجوازات تم رفعها إلى مسار."
    pending = [r for r in records if r.masar_status is None]
    failed = [r for r in records if r.masar_status == "failed"]
    lines = []
    if pending:
        lines.append(f"بانتظار الرفع إلى مسار ({len(pending)}):")
        for r in pending:
            lines.append(f"  - {r.passport_number or str(r.upload_id)}")
    if failed:
        lines.append(f"فشل الرفع ({len(failed)}) — افتح الإضافة وأعد المحاولة:")
        for r in failed:
            lines.append(f"  - {r.passport_number or str(r.upload_id)}")
    return "\n".join(lines)


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


def format_user_plan_text(user: User) -> str:
    return (
        f"المستخدم: {_user_label(user)}\n"
        f"معرف تيليجرام: {user.external_user_id}\n"
        f"الخطة الحالية: {user.plan.value}\n"
        f"حالة الحساب: {user.status.value}\n\n"
        f"{SUPPORT_CONTACT_TEXT}"
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


def _first_value(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return "-"


def _code(value: str | None) -> str:
    escaped = _value(value).replace("\\", "\\\\").replace("`", "'")
    return f"`{escaped}`"


def _join_values(*values: str | None, separator: str = " ") -> str:
    clean = [value.strip() for value in values if value and value.strip()]
    return separator.join(clean) if clean else "-"


def _user_label(user: User) -> str:
    return user.display_name or user.external_user_id
