(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MasarStrings = api;
  root.S = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  return Object.freeze({
    TOPBAR_TITLE: "لوحة الجوازات",
    LOADING: "جارٍ التحميل",
    ERROR_TITLE: "حدث خطأ",
    ERR_UNEXPECTED: "حدث خطأ، حاول مرة أخرى",
    ERR_TIMEOUT: "انتهت المهلة",
    ERR_GENERIC: (message) => (message ? `تعذر إكمال العملية: ${message}` : "تعذر إكمال العملية"),
    ERR_SCAN_PASSPORT: (status) => `فشل قراءة الجواز (${status})`,
    ERR_SCAN_NO_DATA: "لم يتم العثور على بيانات الجواز",
    ERR_SUBMIT_PASSPORT: (status) => `فشل حفظ بيانات الجواز (${status})`,
    ERR_FETCH_CONTACT: (status) => `تعذر جلب بيانات التواصل (${status})`,
    ERR_UPLOAD_ATTACH: (status) => `فشل رفع الصورة (${status})`,
    ERR_UPLOAD_NO_DATA: "لم يتم رفع الصورة",
    ERR_SUBMIT_PERSONAL: (status) => `فشل حفظ البيانات الشخصية (${status})`,
    ERR_SUBMIT_DISCLOSURE: (status) => `فشل إرسال الإقرار (${status})`,
    ERR_IMAGE_FETCH: (status) => `تعذر تحميل الصورة (${status})`,
    ERR_PATCH_FAILED: (status) => `فشل تحديث الحالة (${status})`,

    SETUP_TITLE: "ربط الحساب",
    SETUP_TOKEN_LABEL: "رمز الدخول",
    SETUP_TOKEN_PLACEHOLDER: "الصق الرمز هنا",
    SETUP_SAVE: "حفظ",
    SETUP_RELINK_REQUIRED: "انتهت الجلسة. أضف رمزًا جديدًا للمتابعة",
    SETUP_LOGIN_FAILED: (message) => (message ? `تعذر تسجيل الدخول (${message})` : "تعذر تسجيل الدخول"),

    ACTIVATE_MESSAGE: "افتح صفحة العمل في هذا المتصفح لإكمال الربط",
    OPEN_LOGIN: "افتح صفحة الدخول",
    SESSION_EXPIRED: "انتهت الجلسة",
    MASAR_LOGIN_REQUIRED: "سجّل الدخول من جديد للمتابعة",

    GROUP_TITLE: "اختر المجموعة",
    GROUP_HINT: "افتح قائمة المجموعات وستظهر هنا",
    GROUP_CONFIRM: "تأكيد",
    GROUP_LOAD_FAILED: "تعذر جلب المجموعات",
    GROUP_NONE_FOUND: "لا توجد مجموعات",
    GROUP_CHANGE: "تغيير المجموعة",

    SETTINGS_TITLE: "الإعدادات",
    SETTINGS_EMAIL_LABEL: "البريد الإلكتروني",
    SETTINGS_EMAIL_PLACEHOLDER: "agency@example.com",
    SETTINGS_PHONE_CC_LABEL: "رمز الدولة",
    SETTINGS_PHONE_CC_PLACEHOLDER: "966",
    SETTINGS_PHONE_LABEL: "رقم الجوال",
    SETTINGS_PHONE_PLACEHOLDER: "5XXXXXXXX",
    SETTINGS_SAVE: "حفظ",
    SETTINGS_RESET: "إعادة الربط",

    SECTION_PENDING: "المعلقة",
    SECTION_IN_PROGRESS: "قيد الرفع",
    SECTION_SUBMITTED: "المرفوعة",
    SECTION_FAILED: "الفاشلة",
    SECTION_EMPTY_PENDING: "لا توجد جوازات جاهزة الآن",
    SECTION_EMPTY_IN_PROGRESS: "لا توجد عمليات جارية",
    SECTION_EMPTY_SUBMITTED: "لا توجد جوازات مرفوعة",
    SECTION_EMPTY_FAILED: "لا توجد محاولات فاشلة",

    STATUS_READY: "جاهز",
    STATUS_NEEDS_REVIEW: "يحتاج مراجعة",
    STATUS_IN_PROGRESS: "جاري الرفع",
    STATUS_QUEUED_IN_BATCH: "في الانتظار",
    STATUS_SUBMITTED: "تم الرفع",
    STATUS_SUBMITTED_NEEDS_REVIEW: "تم الرفع - يحتاج مراجعة",
    STATUS_FAILED: "فشل",

    ACTION_SUBMIT: "رفع",
    ACTION_SUBMIT_ALL: "رفع الكل",
    ACTION_RETRY: "إعادة الرفع",
    ACTION_SKIP: "تخطي",
    ACTION_BACK: "رجوع",
    ACTION_SETTINGS: "الإعدادات",
    ACTION_REFRESH: "تحديث",

    HOME_PENDING_LABEL: "جاهز",
    HOME_FAILED_LABEL: "فشل",
    HOME_OFFICE_LABEL: "الحساب",
    HOME_CONTRACT_LABEL: "العقد",
    HOME_GROUP_LABEL: "المجموعة",
    HOME_COUNT_VALUE: (count) => String(count),
    HOME_CONTRACT_EXPIRED: "منتهي",

    SUBMIT_ALL_CONFIRM: (count) => `هل تريد رفع ${count} جواز؟`,
    SUBMIT_SUCCESS: "تم الرفع بنجاح",
    DETAILS_UNAVAILABLE: "تفاصيل غير متوفرة",
    VIEW_DETAILS: "عرض التفاصيل",
    HELP_LINK_LABEL: "مساعدة",

    CTX_CHANGE_ENTITY: "تم تغيير الحساب. حدّث السياق للمتابعة",
    CTX_CHANGE_CONTRACT: "تم تغيير العقد. حدّث السياق للمتابعة",
    CTX_CHANGE_YES: "تحديث الآن",
    CTX_CHANGE_LATER: "لاحقًا",
    CTX_CHANGED_ENTITY: "تم تغيير الحساب",
    CTX_CHANGED_CONTRACT: "تم تغيير العقد",

    NOTIF_BATCH_COMPLETE: "اكتمل رفع الدفعة",
    NOTIF_SESSION_EXPIRED: "انتهت الجلسة",
    NOTIF_CONTEXT_CHANGE: "تم رصد تغيير جديد في الحساب أو العقد",

    CONTRACT_EXPIRED: "انتهى العقد",
    CONTRACT_SELECT_PLACEHOLDER: "اختر العقد",
    CONTRACT_NONE_AVAILABLE: "لا يوجد عقد نشط",

    RECORD_FALLBACK: (id) => `جواز ${id}`,
    REVIEW_SUMMARY: "يحتاج مراجعة",
    THUMBNAIL_LABEL: "جواز",
  });
});
