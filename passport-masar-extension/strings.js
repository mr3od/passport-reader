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
    TOPBAR_KICKER: "مسار العمل",
    LOADING: "جارٍ التحميل",
    LOADING_KICKER: "تهيئة الواجهة",
    LOADING_SUBTITLE: "يجري تجهيز الخطوة الحالية قبل عرضها.",
    LOADING_HINT: "انتظر قليلًا حتى تظهر البيانات.",
    ERROR_TITLE: "حدث خطأ",
    ERROR_KICKER: "تعذر إكمال الخطوة",
    ERROR_SUBTITLE: "يمكنك المحاولة مرة أخرى أو العودة إلى صفحة العمل.",
    ERR_UNEXPECTED: "حدث خطأ، حاول مرة أخرى",
    ERR_TIMEOUT: "انتهت المهلة",
    ERR_GENERIC: (message) => (message ? `تعذر إكمال العملية: ${message}` : "تعذر إكمال العملية"),
    ERR_SCAN_PASSPORT: (status) => `فشل قراءة الجواز (${status})`,
    ERR_SCAN_NO_DATA: "لم يتم العثور على بيانات الجواز",
    ERR_SCAN_IMAGE_UNCLEAR: "صورة الجواز غير واضحة",
    ERR_CONTRACT_NOT_ACTIVE: "لا يوجد عقد نشط",
    ERR_SUBMIT_PASSPORT: (status) => `فشل حفظ بيانات الجواز (${status})`,
    ERR_UPLOAD_ATTACH: (status) => `فشل رفع المرفق (${status})`,
    ERR_UPLOAD_NO_DATA: "فشل رفع المرفق: لم يتم استلام بيانات",
    ERR_FETCH_CONTACT: (status) => `تعذر جلب بيانات التواصل (${status})`,
    ERR_SUBMIT_PERSONAL: (status) => `فشل حفظ البيانات الشخصية (${status})`,
    ERR_SUBMIT_DISCLOSURE: (status) => `فشل إرسال الإقرار (${status})`,
    ERR_IMAGE_FETCH: (status) => `تعذر تحميل الصورة (${status})`,
    ERR_PATCH_FAILED: (status) => `فشل تحديث الحالة (${status})`,

    SETUP_TITLE: "ربط الحساب",
    SETUP_KICKER: "الخطوة الأولى",
    SETUP_SUBTITLE: "أضف رمز الدخول للمتابعة إلى بقية الخطوات.",
    SETUP_TOKEN_LABEL: "رمز الدخول",
    SETUP_TOKEN_PLACEHOLDER: "الصق الرمز هنا",
    SETUP_SAVE: "حفظ",
    SETUP_HELP: "بعد الحفظ ستنتقل الواجهة تلقائيًا إلى الخطوة التالية.",
    SETUP_RELINK_REQUIRED: "انتهت الجلسة. أضف رمزًا جديدًا للمتابعة",
    SETUP_LOGIN_FAILED: (message) => (message ? `تعذر تسجيل الدخول (${message})` : "تعذر تسجيل الدخول"),

    ACTIVATE_KICKER: "خطوة خارجية",
    ACTIVATE_TITLE: "افتح صفحة العمل",
    ACTIVATE_SUBTITLE: "الربط محفوظ. افتح الصفحة في هذا المتصفح لإكمال الجلسة.",
    ACTIVATE_MESSAGE: "افتح صفحة العمل في هذا المتصفح لإكمال الربط",
    OPEN_LOGIN: "افتح صفحة الدخول",
    SESSION_KICKER: "انتهت الجلسة",
    SESSION_EXPIRED: "انتهت الجلسة",
    SESSION_SUBTITLE: "افتح صفحة الدخول ثم ارجع لإكمال العمل من نفس المكان.",
    MASAR_LOGIN_REQUIRED: "سجّل الدخول من جديد للمتابعة",

    SETTINGS_TITLE: "الإعدادات",
    SETTINGS_KICKER: "تحديث البيانات",
    SETTINGS_SUBTITLE: "عدّل بيانات التواصل أو أعد الربط عند الحاجة.",
    SETTINGS_CONTACT_HINT_TITLE: "لماذا نطلب بيانات التواصل؟",
    SETTINGS_CONTACT_HINT_BODY: "تُملأ تلقائيًا في قسم بيانات التواصل بنُوسُك عند رفع كل معتمر. إذا تُركت فارغة، يُصنِّف نُوسُك الطلب كـ «غير مكتمل» حتى بعد اكتمال الرفع.",
    CONTACT_DEFAULTS_NUDGE: "بيانات التواصل غير مُعدَّة — بدونها تُصنِّف نُوسُك الطلبات كـ «غير مكتملة».",
    CONTACT_DEFAULTS_NUDGE_ACTION: "إعداد الآن",
    SETTINGS_EMAIL_LABEL: "البريد الإلكتروني",
    SETTINGS_EMAIL_PLACEHOLDER: "agency@example.com",
    SETTINGS_PHONE_CC_LABEL: "رمز الدولة",
    SETTINGS_PHONE_CC_PLACEHOLDER: "967",
    SETTINGS_PHONE_LABEL: "رقم الجوال",
    SETTINGS_PHONE_PLACEHOLDER: "7XXXXXXXX",
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
    STATUS_MISSING: "غير موجود",
    STATUS_FAILED: "فشل",

    ACTION_SELECTED_COUNT: (count) => `المحدد ${count}`,
    ACTION_SELECT: "تحديد",
    ACTION_BACK: "رجوع",
    ACTION_SETTINGS: "الإعدادات",
    ACTION_REFRESH: "تحديث",
    ACTION_RESUME: "استئناف",
    ACTION_LOAD_MORE: "تحميل المزيد",
    ACTION_MARK_ALL_SELECTABLE: "تحديد المحمل",
    ACTION_SUBMIT_SELECTED: "رفع المحدد",
    ACTION_ARCHIVE_SELECTED: "أرشفة المحدد",
    ARCHIVE_SUCCESS: "تمت الأرشفة",
    ARCHIVE_PARTIAL: (done, total) => `تمت أرشفة ${done} من ${total}`,
    ARCHIVE_FAILED: "تعذر أرشفة الجواز",
    ARCHIVE_RESULT_SUCCESS: "تمت الأرشفة بنجاح",
    ARCHIVE_RESULT_PARTIAL: (succeeded, failed) => `تمت أرشفة ${succeeded} وفشل ${failed}`,
    ARCHIVE_RESULT_FAILED: "فشلت عملية الأرشفة",
    ARCHIVE_RESULT_DISMISS: "إغلاق",
    ACTION_SUBMIT_REQUIRES_RETRYABLE: "الرفع متاح فقط للجوازات المعلقة أو الفاشلة",

    MAIN_KICKER: "جاهز للعمل",
    MAIN_TITLE: "لوحة الجوازات",
    MAIN_SUBTITLE: "مساحة واحدة واضحة للرفع والمتابعة والحالات.",
    MAIN_SUMMARY_TITLE: "السياق الحالي",
    MAIN_SUMMARY_SUBTITLE: "راجع الحساب والعقد قبل بدء الرفع.",
    HOME_PENDING_LABEL: "جاهز",

    HOME_SUBMITTED_LABEL: "مرفوع",
    HOME_FAILED_LABEL: "فشل",
    HOME_OFFICE_LABEL: "الحساب",
    HOME_CONTRACT_LABEL: "العقد",
    HOME_CONTRACT_EXPIRED: "منتهي",

    SUBMIT_ALL_CONFIRM: (count) => `هل تريد رفع ${count} جواز محدد؟`,
    SUBMIT_SUCCESS: "تم الرفع بنجاح",
    SUBMIT_RESUME_UNAVAILABLE: "لا توجد دفعة جاهزة للاستئناف",
    LIST_REFRESH_FAILED: "تعذر تحديث القائمة",
    PROGRESS_BANNER_TITLE: "جارٍ رفع الجوازات",
    PROGRESS_BANNER_SUMMARY: (done, total) => `تم رفع ${done} من ${total}`,
    PROGRESS_BANNER_DETAIL: (activeCount, queuedCount, failedCount = 0) => {
      let detail = "";
      if (activeCount > 0 && queuedCount > 0) {
        detail = `جواز واحد جارٍ رفعه و${queuedCount} في الانتظار`;
      } else if (activeCount > 0) {
        detail = "جواز واحد جارٍ رفعه";
      } else if (queuedCount > 0) {
        detail = `${queuedCount} في الانتظار`;
      }
      if (failedCount > 0) {
        detail = detail ? `${detail} • ${failedCount} فشل` : `${failedCount} فشل`;
      }
      return detail;
    },
    DETAILS_UNAVAILABLE: "تفاصيل غير متوفرة",
    DETAILS_RECORD_MISSING: "هذا الجواز غير موجود",
    DETAILS_OPENING: "جارٍ فتح التفاصيل...",
    DETAILS_OPEN_FAILED: "تعذر فتح التفاصيل",
    DETAILS_OTHER_ENTITY: "يتبع حسابًا آخر",
    DETAILS_OTHER_CONTRACT: "يتبع عقدًا آخر",
    DETAILS_INACCESSIBLE: "التفاصيل غير متاحة في الحساب الحالي",
    DETAILS_OPEN_FROM_OTHER_ENTITY: "افتح الحساب الذي تم الرفع منه",
    DETAILS_OPEN_FROM_OTHER_CONTRACT: "افتح العقد الذي تم الرفع منه",
    VIEW_DETAILS: "عرض التفاصيل",
    HELP_LINK_LABEL: "تواصل معنا",
    HELP_LINK_TITLE: "محتاج مساعدة؟ تواصل مع فريق الدعم مباشرةً على تيليغرام — نرد بسرعة إن شاء الله 🤝",
    HELP_LINK_URL: "https://t.me/mr3od",

    CTX_CHANGE_ENTITY: "تم تغيير الحساب. اختر العقد عند المتابعة",
    CTX_CHANGE_YES: "تحديث الآن",
    CTX_CHANGE_LATER: "لاحقًا",
    CTX_CHANGED_ENTITY: "تم تغيير الحساب",

    CONTRACT_ACTIVE: "العقد نشط",
    CONTRACT_EXPIRED: "انتهى العقد",
    CONTRACT_INACTIVE: "العقد غير نشط",
    CONTRACT_SELECT_LABEL: "العقد",
    CONTRACT_SELECT_PLACEHOLDER: "اختر العقد",
    CONTRACT_NONE_AVAILABLE: "لا يوجد عقد نشط",
    CONTRACT_NONE_AVAILABLE_CURRENT_ACCOUNT: "لا يوجد عقد نشط في الحساب الحالي",
    CONTRACT_ACTION_REQUIRED: "اختر العقد أولًا",
    CONTRACT_INACTIVE_ACTION_REQUIRED: "اختر عقدًا نشطًا أولًا",

    RECORD_FALLBACK: (id) => `جواز ${id}`,
    REVIEW_SUMMARY: "يحتاج مراجعة",
    THUMBNAIL_LABEL: "جواز",
  });
});
