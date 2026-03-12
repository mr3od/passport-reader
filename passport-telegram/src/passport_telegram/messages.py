from __future__ import annotations

from passport_core import PassportWorkflowResult


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


def processing_error_text() -> str:
    return "حدث خطأ أثناء المعالجة. حاول مرة أخرى بصورة أوضح."


def _value(value: str | None) -> str:
    return value or "-"


def _join_values(*values: str | None, separator: str = " ") -> str:
    clean = [value.strip() for value in values if value and value.strip()]
    return separator.join(clean) if clean else "-"
