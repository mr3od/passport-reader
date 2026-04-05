from __future__ import annotations

from datetime import UTC

from passport_platform import (
    IssuedTempToken,
    QuotaDecision,
    TrackedProcessingResult,
    UserUsageReport,
)
from passport_platform.models.user import User
from passport_platform.schemas.results import UserRecord

SUPPORT_CONTACT_TEXT = "للاستفسارات أو طلب تغيير الخطة، تواصل مع @mr3od أو @naaokun."


def welcome_text() -> str:
    return (
        "أهلًا وسهلًا.\n\n"
        "أرسل صورة الجواز الآن، وسيتم فحصها واستخراج البيانات مباشرة.\n\n"
        "مهم: أحيانًا ضغط الصورة داخل تيليجرام يسبب ضعف في نتيجة المعالجة، لذلك إذا كانت النتيجة غير دقيقة فأرسلها كملف أو بصورة أوضح.\n\n"
        "إذا أردت الاستفادة الكاملة من الخدمة ومتابعة رفع الحالات إلى Nusuk، فالإضافة هي الخيار الأفضل:\n"
        "/extension - تحميل الإضافة وطريقة التثبيت\n\n"
        "الأوامر المهمة:\n"
        "/me - عرض حالة الحساب والاستخدام\n"
        "/token - إصدار رمز الدخول للإضافة\n"
        "/masar - متابعة الحالات المعلقة أو الفاشلة في Nusuk\n"
        "/help - طريقة الاستخدام\n\n"
        f"{SUPPORT_CONTACT_TEXT}"
    )


def help_text() -> str:
    return (
        "طريقة الاستخدام باختصار:\n"
        "1. أرسل صورة الجواز كصورة أو كملف.\n"
        "2. تأكد أن الصورة واضحة وتُظهر كامل الصفحة.\n"
        "3. يمكنك إرسال أكثر من صورة في دفعة واحدة.\n"
        "4. أحيانًا ضغط الصورة داخل تيليجرام يضعف المعالجة، فإذا أمكن أرسلها كملف أو بصورة أوضح.\n"
        "5. إذا أردت الطريقة الكاملة ومتابعة الحالات إلى Nusuk، ثبّت الإضافة من /extension.\n\n"
        "الأوامر:\n"
        "/me - حالة الحساب والاستخدام\n"
        "/token - رمز الدخول للإضافة\n"
        "/masar - متابعة الحالات المعلقة أو الفاشلة في Nusuk\n"
        "/extension - تحميل الإضافة\n\n"
        "الملفات المدعومة: JPG, JPEG, PNG, WEBP, TIF, TIFF\n\n"
        f"{SUPPORT_CONTACT_TEXT}"
    )


def extension_installing_text() -> str:
    """Sent immediately while the ZIP is being fetched."""
    return "⏳ جاري تجهيز الإضافة لك. انتظر قليلًا..."


def extension_step1_caption() -> str:
    """Caption for the chrome://extensions screenshot."""
    return (
        "الخطوة 1️⃣: افتح Chrome وانتقل إلى chrome://extensions\n"
        "فعّل وضع المطور (Developer Mode) من أعلى الصفحة."
    )


def extension_step2_caption() -> str:
    """Caption for the Load unpacked screenshot."""
    return (
        "الخطوة 2️⃣: فك ضغط الملف أولًا\n"
        "ثم انقر على «Load unpacked» واختر المجلد الذي ظهر بعد فك الضغط."
    )


def extension_step3_caption() -> str:
    """Caption for the installed extension screenshot."""
    return "الخطوة 3️⃣: تأكد من ظهور الإضافة في القائمة ✅"


def extension_fetch_error_text() -> str:
    """Sent when the ZIP cannot be fetched from GitHub."""
    return "⚠️ تعذّر تحميل الإضافة في الوقت الحالي. يرجى المحاولة لاحقًا أو التواصل مع الدعم."


def batch_started_text(total: int) -> str:
    if total == 1:
        return "تم استلام الصورة، وجاري فحصها الآن."
    return f"تم استلام {total} صور، وجاري فحصها الآن."


def batch_limit_exceeded_text(*, total: int, limit: int) -> str:
    return (
        f"عدد الصور المرسلة ({total}) يتجاوز الحد المسموح في الدفعة الواحدة ({limit}).\n"
        "قسّم الصور إلى دفعات أصغر ثم أعد الإرسال."
    )


def format_failure_text(result: TrackedProcessingResult, *, position: int, total: int) -> str:
    prefix = f"الصورة {position} من {total}\n" if total > 1 else ""

    if not result.is_passport:
        return (
            prefix + "لم أتمكن من التأكد أن الصورة لجواز واضح وجاهز للمعالجة. "
            "أعد الإرسال بصورة أوضح وتأكد أن كامل صفحة الجواز ظاهرة. وإذا كانت الصورة مضغوطة من تيليجرام فالأفضل إرسالها كملف."
        )

    return prefix + "لم تكتمل معالجة الصورة الحالية. أعد المحاولة بصورة أوضح."


def format_success_text(result: TrackedProcessingResult, *, position: int, total: int) -> str:
    prefix = f"الصورة {position} من {total}\n" if total > 1 else ""
    data = result.extracted_data
    if data is None:
        return prefix + "تعذر استخراج البيانات من الصورة الحالية."

    lines = [
        prefix + "تم فحص الجواز بنجاح.",
        f"حالة المراجعة: {_code(_review_status_label(result.review_status))}",
        f"مستوى الثقة: {_code(_confidence_label(result.confidence_overall))}",
        f"ملاحظات التحقق: {_code(_warnings_label(len(result.warnings)))}",
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


def processing_error_text() -> str:
    return f"حدث خطأ أثناء المعالجة. أعد المحاولة بصورة أوضح. {SUPPORT_CONTACT_TEXT}"


def processing_busy_text() -> str:
    return "الخدمة عليها ضغط حاليًا. أعد المحاولة بعد قليل."


def quota_exceeded_text(decision: QuotaDecision) -> str:
    return (
        "وصلت للحد المسموح في الخطة الحالية.\n"
        f"المتبقي من رفع الصور هذا الشهر: {decision.remaining_uploads}\n"
        f"المتبقي من المعالجات الناجحة هذا الشهر: {decision.remaining_successes}\n\n"
        f"{SUPPORT_CONTACT_TEXT}"
    )


def user_blocked_text() -> str:
    return f"تم إيقاف الحساب مؤقتًا عن استخدام الخدمة. {SUPPORT_CONTACT_TEXT}"


def temp_token_text(issued: IssuedTempToken) -> str:
    expires_at = issued.expires_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "هذا رمز دخول مؤقت للإضافة.\n"
        "الرمز:\n"
        f"`{issued.token}`\n"
        f"ينتهي في: {expires_at}\n"
        "هذا الرمز صالح للاستخدام مرة واحدة فقط.\n"
        "الصقه في شاشة تسجيل الدخول داخل الإضافة."
    )


def format_masar_status_text(records: list[UserRecord]) -> str:
    if not records:
        return "كل الحالات تم رفعها إلى Nusuk."
    pending = [r for r in records if r.masar_status is None]
    failed = [r for r in records if r.masar_status == "failed"]
    lines = []
    if pending:
        lines.append(f"بانتظار الرفع إلى Nusuk ({len(pending)}):")
        for r in pending:
            lines.append(f"  - {r.passport_number or str(r.upload_id)}")
    if failed:
        lines.append(f"فشل الرفع إلى Nusuk ({len(failed)}) — افتح الإضافة وأكمل من هناك:")
        for r in failed:
            lines.append(f"  - {r.passport_number or str(r.upload_id)}")
    return "\n".join(lines)


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
        f"المتبقي من المعالجات الناجحة: {report.quota_decision.remaining_successes}\n\n"
        "للاستخدام الكامل ومتابعة الحالات إلى Nusuk، ثبّت الإضافة من /extension"
    )


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


def _review_status_label(value: str) -> str:
    labels = {
        "auto": "جاهزة للرفع",
        "reviewed": "تمت المراجعة",
        "needs_review": "تحتاج مراجعة قبل الرفع",
    }
    return labels.get(value, "تحتاج مراجعة قبل الرفع")


def _confidence_label(value: float | None) -> str:
    if value is None:
        return "غير متوفر"
    return f"{round(value * 100)}%"


def _warnings_label(count: int) -> str:
    if count <= 0:
        return "لا توجد ملاحظات"
    if count == 1:
        return "يوجد تنبيه واحد ويحتاج مراجعة"
    return f"توجد {count} تنبيهات وتحتاج مراجعة"
