const S = {
  // ── General ───────────────────────────────────────────────────────────────────
  TOPBAR_TITLE: "تسجيل المعتمرين",
  LOADING:      "جارٍ التحميل…",

  // ── Context panel ─────────────────────────────────────────────────────────────
  CTX_SYNCED_NOW: "تم التحديث الآن",
  CTX_SYNCED_AGO: (n) => `آخر تحديث منذ ${n} د`,
  CTX_NOT_SYNCED: "لم يتم التحديث",
  CTX_SYNCING:    "جارٍ التحديث…",

  // ── Contract state labels ──────────────────────────────────────────────────────
  CONTRACT_ACTIVE:        "نشط",
  CONTRACT_EXPIRES_TODAY: "ينتهي اليوم",
  CONTRACT_EXPIRED:       "منتهٍ",

  // ── Queue ─────────────────────────────────────────────────────────────────────
  PENDING_COUNT:     (n) => `جوازات معلقة (${n})`,
  QUEUE_EMPTY:       "لا توجد جوازات معلقة",
  QUEUE_LOAD_FAILED: (d) => `تعذر تحميل القائمة (${d})`,
  BTN_SUBMIT:        "رفع",
  BTN_SKIP:          "تخطي",
  SUBMITTING:        "جارٍ الرفع…",
  SUBMIT_SUCCESS:    "تم الرفع بنجاح",
  REVIEW_REQUIRED:   "تحتاج مراجعة قبل الرفع",
  REVIEW_AUTO:       "جاهزة للرفع",
  REVIEW_DONE:       "تمت المراجعة",
  REVIEW_CONFIRM:    "هذه البيانات تحتاج مراجعة قبل الرفع. هل تؤكد المتابعة؟",
  REVIEW_UPDATE_FAILED: (d) => `تعذر تحديث حالة المراجعة (${d})`,
  ERR_SESSION:       "انتهت الجلسة — افتح منصة نسك وأعد المحاولة",
  ERR_GENERIC:       (msg) => `خطأ: ${msg}`,

  // ── Record display name fallback ───────────────────────────────────────────────
  RECORD_FALLBACK: (id) => `جواز #${id}`,

  // ── Group select ──────────────────────────────────────────────────────────────
  GROUP_LOAD_FAILED: "تعذر جلب المجموعات",
  GROUP_NONE_FOUND:  "لا توجد مجموعات",

  // ── Background: Masar submission step errors ───────────────────────────────────
  // Returned in { error: S.* } objects and shown to agencies in the popup.
  // background.js log()/logError() calls stay English — developer-only.
  ERR_SCAN_PASSPORT:     (s) => `فشل قراءة الجواز (${s})`,
  ERR_SCAN_NO_DATA:      "لم تُعد قراءة الجواز بيانات",
  ERR_SUBMIT_PASSPORT:   (s) => `فشل رفع البيانات (${s})`,
  ERR_FETCH_CONTACT:     (s) => `فشل جلب بيانات التواصل (${s})`,
  ERR_UPLOAD_ATTACH:     (s) => `فشل رفع الصورة (${s})`,
  ERR_UPLOAD_NO_DATA:    "لم يُعد رفع الصورة بيانات",
  ERR_SUBMIT_PERSONAL:   (s) => `فشل حفظ البيانات الشخصية (${s})`,
  ERR_SUBMIT_DISCLOSURE: (s) => `فشل إرسال نموذج الإفصاح (${s})`,
  ERR_IMAGE_FETCH:       (s) => `تعذر تحميل الصورة (${s})`,
  ERR_PATCH_FAILED:      (s) => `فشل تحديث الحالة (${s})`,

  // ── Generic errors ────────────────────────────────────────────────────────────
  ERR_UNEXPECTED: "حدث خطأ، حاول مجدداً",
  ERR_TIMEOUT:    "انتهت مهلة الطلب",
};
