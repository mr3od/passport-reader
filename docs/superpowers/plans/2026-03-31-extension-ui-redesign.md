# Extension UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the extension popup from a flat pending queue into a tabbed four-section workspace (Pending / In Progress / Submitted / Failed) with batch submission, context-change notifications, contract selection, click-to-redirect, and review-gate removal.

**Architecture:** Backend adds `masar_detail_id` column and relaxes the submission gate to allow `needs_review` records. Extension gets 6 new JS modules (strings, status, queue-filter, badge, notifications, context-change, contract-select), a rewritten popup with tab navigation and batch submission, and a background.js upgrade with step 7, session-storage batch state, and context-change detection.

**Tech Stack:** Python (FastAPI, SQLite, pytest) for backend; vanilla JS (Chrome MV3 APIs) for extension; no build tooling.

**Design reference split:**
- `docs/final-design-proposal.html` → preserved final popup mock used during redesign
- Current code + spec + HARs → behavior and data contracts (if conflict, behavior wins)

---

## File Map

### Backend — passport-platform

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/passport_platform/db.py:54-63` | Add `masar_detail_id TEXT` to `masar_submissions` |
| Modify | `src/passport_platform/models/upload.py:40-48` | Add `masar_detail_id` to `MasarSubmission` dataclass |
| Modify | `src/passport_platform/repositories/records.py:10-48,105-145,168-195` | Add `masar_detail_id` to SQL projections, INSERT, row mapper |
| Modify | `src/passport_platform/services/records.py:23-40,45-53` | Pass through `masar_detail_id`; relax gate |
| Modify | `src/passport_platform/schemas/results.py:152-174` | Add `masar_detail_id` to `UserRecord` |
| Modify | `migrations/0001_initial.sql` | Sync baseline with `db.py` |
| Modify | `tests/test_upload_service.py` | Verify new column created |

### Backend — passport-api

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/passport_api/schemas.py:26-50` | Add `masar_detail_id` to `RecordResponse` and `MasarStatusUpdate` |
| Modify | `src/passport_api/routes/records.py:96-129,158-178` | Pass through `masar_detail_id` in PATCH; add to response mapper |
| Modify | `tests/test_api.py:245-324` | Update review gate test: `needs_review` now succeeds directly |

### Extension — passport-masar-extension

| Action | File | Responsibility |
|--------|------|---------------|
| Rewrite | `strings.js` | All Arabic UI strings, drop legacy review-gate keys |
| Create | `status.js` | `getStatusLabel()`, `getStatusColor()` |
| Create | `queue-filter.js` | `filterQueueSections()` — sorts records into 4 tabs |
| Create | `badge.js` | `computeBadgeState()`, `applyBadge()` |
| Create | `notifications.js` | `notify()`, dedup, Chrome notification API |
| Create | `context-change.js` | `detectContextChange()`, `applyContextChange()`, submission state machine |
| Create | `contract-select.js` | `fetchContracts()`, `resolveContractSelection()` |
| Rewrite | `popup.html` | Tab bar, context-change banner, contract dropdown, home summary, 4 sections |
| Rewrite | `popup.css` | Tab styles, rich card layout, context banner, badge colors |
| Rewrite | `popup.js` | Tab navigation, Submit All batch, individual submit, click-to-redirect, contract dropdown |
| Modify | `background.js` | Step 7 (GetMutamerList), session-storage batch state, context-change detection, FETCH_ALL_RECORDS, SUBMIT_BATCH |
| Modify | `manifest.json` | Add `notifications` permission |

---

## Task 1: Platform — Add `masar_detail_id` column

**Files:**
- Modify: `passport-platform/src/passport_platform/db.py:54-63`
- Modify: `passport-platform/migrations/0001_initial.sql`

- [ ] **Step 1: Add column to SCHEMA_SQL in db.py**

In `passport-platform/src/passport_platform/db.py`, update the `masar_submissions` table:

```python
CREATE TABLE IF NOT EXISTS masar_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    mutamer_id TEXT,
    scan_result_json TEXT,
    masar_detail_id TEXT,
    submitted_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (upload_id) REFERENCES uploads(id) ON DELETE CASCADE
);
```

- [ ] **Step 2: Sync migration baseline**

Update `passport-platform/migrations/0001_initial.sql` to match the new `SCHEMA_SQL` — add `masar_detail_id TEXT` column in the same position.

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `uv run pytest passport-platform/tests/test_upload_service.py -v`
Expected: PASS — `test_initialize_creates_v2_processing_results_and_masar_tables` still passes (CREATE IF NOT EXISTS is idempotent).

- [ ] **Step 4: Commit**

```bash
git add passport-platform/src/passport_platform/db.py passport-platform/migrations/0001_initial.sql
git commit -m "feat(platform): add masar_detail_id column to masar_submissions"
```

---

## Task 2: Platform — Add `masar_detail_id` to model, repo, service, schema

**Files:**
- Modify: `passport-platform/src/passport_platform/models/upload.py:40-48`
- Modify: `passport-platform/src/passport_platform/repositories/records.py:10-48,105-145,168-195`
- Modify: `passport-platform/src/passport_platform/services/records.py:23-40`
- Modify: `passport-platform/src/passport_platform/schemas/results.py:152-174`

- [ ] **Step 1: Add field to MasarSubmission dataclass**

In `passport-platform/src/passport_platform/models/upload.py`, add to `MasarSubmission`:

```python
@dataclass(slots=True)
class MasarSubmission:
    id: int
    upload_id: int
    status: str
    mutamer_id: str | None
    scan_result_json: str | None
    masar_detail_id: str | None
    submitted_at: datetime | None
    created_at: datetime
```

- [ ] **Step 2: Add field to UserRecord dataclass**

In `passport-platform/src/passport_platform/schemas/results.py`, add to `UserRecord` (after `masar_scan_result`):

```python
@dataclass(slots=True)
class UserRecord:
    upload_id: int
    user_id: int
    filename: str
    mime_type: str
    source_ref: str
    upload_status: UploadStatus
    created_at: datetime
    completed_at: datetime | None
    is_passport: bool | None
    is_complete: bool | None
    review_status: str | None
    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    passport_number: str | None
    passport_image_uri: str | None
    confidence_overall: float | None
    extraction_result: dict[str, Any] | None
    error_code: str | None
    masar_status: str | None
    masar_mutamer_id: str | None
    masar_scan_result: dict[str, Any] | None
    masar_detail_id: str | None
```

- [ ] **Step 3: Update repository SQL projections**

In `passport-platform/src/passport_platform/repositories/records.py`:

Add `ms1.masar_detail_id AS masar_detail_id` to `_LATEST_MASAR_SUBMISSION_JOIN` inner SELECT:

```python
_LATEST_MASAR_SUBMISSION_JOIN = """
LEFT JOIN (
    SELECT
        ms1.upload_id AS upload_id,
        ms1.status AS masar_status,
        ms1.mutamer_id AS masar_mutamer_id,
        ms1.scan_result_json AS masar_scan_result_json,
        ms1.masar_detail_id AS masar_detail_id
    FROM masar_submissions ms1
    INNER JOIN (
        SELECT upload_id, MAX(id) AS max_id
        FROM masar_submissions
        GROUP BY upload_id
    ) ms2 ON ms1.id = ms2.max_id
) ms ON ms.upload_id = uploads.id
"""
```

Add `ms.masar_detail_id AS masar_detail_id` to `_USER_RECORD_COLUMNS`:

```python
_USER_RECORD_COLUMNS = """
    uploads.id AS upload_id,
    uploads.user_id AS user_id,
    uploads.filename AS filename,
    uploads.mime_type AS mime_type,
    uploads.source_ref AS source_ref,
    uploads.status AS upload_status,
    uploads.created_at AS created_at,
    processing_results.completed_at AS completed_at,
    processing_results.is_passport AS is_passport,
    processing_results.is_complete AS is_complete,
    processing_results.review_status AS review_status,
    processing_results.reviewed_by_user_id AS reviewed_by_user_id,
    processing_results.reviewed_at AS reviewed_at,
    processing_results.passport_number AS passport_number,
    processing_results.passport_image_uri AS passport_image_uri,
    processing_results.confidence_overall AS confidence_overall,
    processing_results.extraction_result_json AS extraction_result_json,
    processing_results.error_code AS error_code,
    ms.masar_status AS masar_status,
    ms.masar_mutamer_id AS masar_mutamer_id,
    ms.masar_scan_result_json AS masar_scan_result_json,
    ms.masar_detail_id AS masar_detail_id
"""
```

- [ ] **Step 4: Update insert_masar_submission**

Add `masar_detail_id` parameter and include in INSERT:

```python
def insert_masar_submission(
    self,
    *,
    upload_id: int,
    user_id: int,
    status: str,
    masar_mutamer_id: str | None,
    masar_scan_result_json: str | None,
    masar_detail_id: str | None = None,
) -> bool:
    created_at = datetime.now(UTC)
    submitted_at = created_at if status == "submitted" else None
    with self.db.connect() as conn:
        upload_row = conn.execute(
            "SELECT id FROM uploads WHERE id = ? AND user_id = ?",
            (upload_id, user_id),
        ).fetchone()
        if upload_row is None:
            return False
        conn.execute(
            """
            INSERT INTO masar_submissions (
                upload_id,
                status,
                mutamer_id,
                scan_result_json,
                masar_detail_id,
                submitted_at,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                status,
                masar_mutamer_id,
                masar_scan_result_json,
                masar_detail_id,
                submitted_at.isoformat() if submitted_at is not None else None,
                created_at.isoformat(),
            ),
        )
        conn.commit()
    return True
```

- [ ] **Step 5: Update _row_to_user_record**

Add `masar_detail_id` to the mapper:

```python
def _row_to_user_record(row) -> UserRecord:
    return UserRecord(
        upload_id=int(row["upload_id"]),
        user_id=int(row["user_id"]),
        filename=row["filename"],
        mime_type=row["mime_type"],
        source_ref=row["source_ref"],
        upload_status=UploadStatus(row["upload_status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"]) if row["completed_at"] is not None else None
        ),
        is_passport=_nullable_bool(row["is_passport"]),
        is_complete=_nullable_bool(row["is_complete"]),
        review_status=row["review_status"],
        reviewed_by_user_id=row["reviewed_by_user_id"],
        reviewed_at=(
            datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] is not None else None
        ),
        passport_number=row["passport_number"],
        passport_image_uri=row["passport_image_uri"],
        confidence_overall=row["confidence_overall"],
        extraction_result=_parse_json(row["extraction_result_json"]),
        error_code=row["error_code"],
        masar_status=row["masar_status"],
        masar_mutamer_id=row["masar_mutamer_id"],
        masar_scan_result=_parse_json(row["masar_scan_result_json"]),
        masar_detail_id=row["masar_detail_id"],
    )
```

- [ ] **Step 6: Update service passthrough**

In `passport-platform/src/passport_platform/services/records.py`, update `update_masar_status`:

```python
def update_masar_status(
    self,
    upload_id: int,
    user_id: int,
    status: str,
    masar_mutamer_id: str | None,
    masar_scan_result: dict | None,
    masar_detail_id: str | None = None,
) -> bool:
    masar_scan_result_json = (
        json.dumps(masar_scan_result) if masar_scan_result is not None else None
    )
    return self.records.insert_masar_submission(
        upload_id=upload_id,
        user_id=user_id,
        status=status,
        masar_mutamer_id=masar_mutamer_id,
        masar_scan_result_json=masar_scan_result_json,
        masar_detail_id=masar_detail_id,
    )
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest passport-platform/tests/ -v`
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add passport-platform/src/passport_platform/models/upload.py \
       passport-platform/src/passport_platform/repositories/records.py \
       passport-platform/src/passport_platform/services/records.py \
       passport-platform/src/passport_platform/schemas/results.py
git commit -m "feat(platform): wire masar_detail_id through model, repo, service, schema"
```

---

## Task 3: Platform — Relax submission gate for needs_review

**Files:**
- Modify: `passport-platform/src/passport_platform/services/records.py:45-53`

- [ ] **Step 1: Update assert_submission_allowed**

```python
def assert_submission_allowed(self, *, upload_id: int, user_id: int) -> None:
    record = self.records.get_user_record(user_id, upload_id)
    if record is None:
        return
    if not record.is_complete:
        raise ReviewRequiredError()
    if record.review_status in {"auto", "reviewed", "needs_review"}:
        return
    raise ReviewRequiredError()
```

- [ ] **Step 2: Run tests — expect test_review_gate test to need updating**

Run: `uv run pytest passport-platform/tests/ passport-api/tests/ -v`
Expected: Platform tests PASS. API test `test_review_gate_before_masar_submit` may now fail because it expects 409 for `needs_review` — that's fixed in Task 5.

- [ ] **Step 3: Commit**

```bash
git add passport-platform/src/passport_platform/services/records.py
git commit -m "feat(platform): allow needs_review records to submit without prior review"
```

---

## Task 4: API — Add masar_detail_id to schemas and route

**Files:**
- Modify: `passport-api/src/passport_api/schemas.py:26-50`
- Modify: `passport-api/src/passport_api/routes/records.py:96-129,158-178`

- [ ] **Step 1: Update API schemas**

In `passport-api/src/passport_api/schemas.py`:

Add `masar_detail_id` to `RecordResponse`:

```python
class RecordResponse(BaseModel):
    upload_id: int
    user_id: int
    filename: str
    mime_type: str
    source_ref: str
    upload_status: str
    created_at: datetime
    completed_at: datetime | None
    is_passport: bool | None
    is_complete: bool | None
    review_status: str | None
    passport_number: str | None
    passport_image_uri: str | None
    confidence_overall: float | None
    review_summary: str | None
    extraction_result: dict[str, Any] | None
    error_code: str | None
    masar_status: str | None
    masar_detail_id: str | None
```

Add `masar_detail_id` to `MasarStatusUpdate`:

```python
class MasarStatusUpdate(BaseModel):
    status: str
    masar_mutamer_id: str | None = None
    masar_scan_result: dict[str, Any] | None = None
    masar_detail_id: str | None = None
```

- [ ] **Step 2: Update route — PATCH passthrough**

In `passport-api/src/passport_api/routes/records.py`, update `update_masar_status` to pass `masar_detail_id`:

```python
    updated = services.records.update_masar_status(
        upload_id=upload_id,
        user_id=authenticated.user.id,
        status=body.status,
        masar_mutamer_id=body.masar_mutamer_id,
        masar_scan_result=body.masar_scan_result,
        masar_detail_id=body.masar_detail_id,
    )
```

- [ ] **Step 3: Update route — response mapper**

Update `_record_to_response` to include `masar_detail_id`:

```python
def _record_to_response(record) -> RecordResponse:
    return RecordResponse(
        upload_id=record.upload_id,
        user_id=record.user_id,
        filename=record.filename,
        mime_type=record.mime_type,
        source_ref=record.source_ref,
        upload_status=record.upload_status.value,
        created_at=record.created_at,
        completed_at=record.completed_at,
        is_passport=record.is_passport,
        is_complete=record.is_complete,
        review_status=record.review_status,
        passport_number=record.passport_number,
        passport_image_uri=record.passport_image_uri,
        confidence_overall=record.confidence_overall,
        review_summary=_review_summary(record),
        extraction_result=record.extraction_result,
        error_code=record.error_code,
        masar_status=record.masar_status,
        masar_detail_id=record.masar_detail_id,
    )
```

- [ ] **Step 4: Commit**

```bash
git add passport-api/src/passport_api/schemas.py passport-api/src/passport_api/routes/records.py
git commit -m "feat(api): add masar_detail_id to schemas and PATCH route"
```

---

## Task 5: API — Update review gate test

**Files:**
- Modify: `passport-api/tests/test_api.py:245-324`

- [ ] **Step 1: Update test_review_gate_before_masar_submit**

The test currently asserts that submitting a `needs_review` record returns 409 and requires a prior `MARK_REVIEWED`. With the gate relaxed, the first submit should succeed directly. Replace the test:

```python
def test_review_gate_before_masar_submit(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "platform.sqlite3"
    monkeypatch.setenv("PASSPORT_PLATFORM_DB_PATH", str(db_path))
    monkeypatch.setenv("PASSPORT_PLATFORM_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    services = build_services()
    db = Database(db_path)
    users = UserService(UsersRepository(db))
    uploads = UploadService(UploadsRepository(db), UsageRepository(db))
    user = users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.TELEGRAM,
            external_user_id="12345",
            display_name="Agency A",
        )
    )
    upload = uploads.register_upload(
        RegisterUploadCommand(
            user_id=user.id,
            channel=ChannelName.TELEGRAM,
            filename="passport.jpg",
            mime_type="image/jpeg",
            source_ref="telegram://chat/1/message/2/file/abc",
        )
    )
    uploads.record_processing_result(
        user.id,
        RecordProcessingResultCommand(
            upload_id=upload.id,
            is_passport=True,
            is_complete=True,
            review_status="needs_review",
            passport_number="12345678",
            passport_image_uri="/tmp/original.jpg",
            confidence_overall=0.71,
            extraction_result_json='{"data":{"PassportNumber":"12345678"},"warnings":["requires_review"]}',
            completed_at=datetime(2026, 3, 13, 10, 1, tzinfo=UTC),
        ),
    )
    temp = services.auth.issue_temp_token(user.id)

    app = create_app()
    app.dependency_overrides[get_api_services] = lambda: services
    client = TestClient(app)

    exchange = client.post("/auth/exchange", json={"token": temp.token})
    assert exchange.status_code == 200
    session_token = exchange.json()["session_token"]
    headers = {"Authorization": f"Bearer {session_token}"}

    # needs_review records can now submit directly — no prior MARK_REVIEWED needed
    submit = client.patch(
        f"/records/{upload.id}/masar-status",
        headers=headers,
        json={
            "status": "submitted",
            "masar_mutamer_id": "M-1",
            "masar_scan_result": {"ok": True},
            "masar_detail_id": "detail-abc-123",
        },
    )
    assert submit.status_code == 200
    assert submit.json()["masar_status"] == "submitted"
    assert submit.json()["masar_detail_id"] == "detail-abc-123"
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest passport-platform/tests/ passport-api/tests/ -v`
Expected: All PASS.

- [ ] **Step 3: Commit**

```bash
git add passport-api/tests/test_api.py
git commit -m "test(api): update review gate test — needs_review submits directly, verify masar_detail_id"
```

---

## Task 6: Extension — Rewrite strings.js

**Files:**
- Rewrite: `passport-masar-extension/strings.js`

- [ ] **Step 1: Rewrite strings.js**

Replace the entire file. Drop legacy keys (`REVIEW_CONFIRM`, `REVIEW_UPDATE_FAILED`, `REVIEW_REQUIRED`). Add new tab, badge, and context-change keys:

```javascript
const S = Object.freeze({
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

  // ── Tab labels ────────────────────────────────────────────────────────────────
  SECTION_PENDING:     "معلّقة",
  SECTION_IN_PROGRESS: "قيد الرفع",
  SECTION_SUBMITTED:   "تم الرفع",
  SECTION_FAILED:      "فشل",

  // ── Status badges ─────────────────────────────────────────────────────────────
  STATUS_READY:                  "جاهز",
  STATUS_NEEDS_REVIEW:           "يحتاج مراجعة",
  STATUS_IN_PROGRESS:            "جاري الرفع",
  STATUS_QUEUED_IN_BATCH:        "في الانتظار",
  STATUS_SUBMITTED:              "تم الرفع",
  STATUS_SUBMITTED_NEEDS_REVIEW: "تم الرفع - يحتاج مراجعة",
  STATUS_FAILED:                 "فشل",

  // ── Actions ───────────────────────────────────────────────────────────────────
  ACTION_SUBMIT:     "رفع",
  ACTION_SUBMIT_ALL: (n) => `رفع الكل (${n})`,
  ACTION_RETRY:      "إعادة المحاولة",
  ACTION_SKIP:       "تخطي",

  // ── Submit All confirmation ───────────────────────────────────────────────────
  SUBMIT_ALL_CONFIRM: (n) => `هل تريد رفع ${n} جواز؟`,

  // ── Click-to-redirect ─────────────────────────────────────────────────────────
  VIEW_DETAILS:        "عرض التفاصيل",
  DETAILS_UNAVAILABLE: "تفاصيل غير متوفرة",

  // ── Context change ────────────────────────────────────────────────────────────
  CTX_CHANGE_PROMPT:   "تم اكتشاف تغيير في السياق",
  CTX_CHANGED_ENTITY:  "تم تغيير الحساب في منصة نسك",
  CTX_CHANGED_CONTRACT:"تم تغيير العقد في منصة نسك",
  CTX_CHANGE_YES:      "تحديث",
  CTX_CHANGE_LATER:    "لاحقًا",

  // ── Notifications ─────────────────────────────────────────────────────────────
  NOTIF_BATCH_COMPLETE:  "تم الانتهاء من رفع الدفعة",
  NOTIF_SESSION_EXPIRED: "انتهت جلسة منصة نسك",

  // ── Queue ─────────────────────────────────────────────────────────────────────
  QUEUE_EMPTY:       "لا توجد جوازات معلقة",
  QUEUE_LOAD_FAILED: (d) => `تعذر تحميل القائمة (${d})`,

  // ── Record display name fallback ───────────────────────────────────────────────
  RECORD_FALLBACK: (id) => `جواز #${id}`,

  // ── Group select ──────────────────────────────────────────────────────────────
  GROUP_LOAD_FAILED: "تعذر جلب المجموعات",
  GROUP_NONE_FOUND:  "لا توجد مجموعات",

  // ── Setup / login ───────────────────────────────────────────────────────────
  SETUP_RELINK_REQUIRED: "انتهت جلسة الربط — الصق رمزًا جديدًا من /token",
  SETUP_LOGIN_FAILED: (msg) => msg ? `تعذر تسجيل الدخول (${msg})` : "تعذر تسجيل الدخول",
  MASAR_LOGIN_REQUIRED: "جلسة الدخول غير متاحة — افتح صفحة الدخول وسجّل الدخول",
  OPEN_MASAR_BUTTON: "افتح صفحة الدخول",

  // ── Background: Masar submission step errors ───────────────────────────────────
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
  ERR_DETAIL_FETCH:      (s) => `تعذر جلب تفاصيل المعتمر (${s})`,

  // ── Generic errors ────────────────────────────────────────────────────────────
  ERR_UNEXPECTED: "حدث خطأ، حاول مجدداً",
  ERR_TIMEOUT:    "انتهت مهلة الطلب",

  // ── Contract expired ──────────────────────────────────────────────────────────
  CONTRACT_EXPIRED_BLOCK: "انتهى العقد — لن تقبل منصة نسك أي تسجيلات",

  // ── Help link ─────────────────────────────────────────────────────────────────
  HELP_LINK_LABEL: "المساعدة",
});
```

- [ ] **Step 2: Commit**

```bash
git add passport-masar-extension/strings.js
git commit -m "feat(extension): rewrite strings.js — add tab/badge/context strings, drop review-gate keys"
```

---

## Task 7: Extension — Create status.js

**Files:**
- Create: `passport-masar-extension/status.js`

- [ ] **Step 1: Create status.js**

```javascript
// Status label and color for a record, given its state and whether it's in the active batch.
// Priority: failed → submitted+needs_review → submitted → in_progress → pending+needs_review → ready.

function getStatusLabel({ upload_status, masar_status, review_status, inProgress }) {
  if (upload_status === "failed" || masar_status === "failed") return S.STATUS_FAILED;
  if (masar_status === "submitted" && review_status === "needs_review") return S.STATUS_SUBMITTED_NEEDS_REVIEW;
  if (masar_status === "submitted") return S.STATUS_SUBMITTED;
  if (inProgress) return S.STATUS_IN_PROGRESS;
  if (review_status === "needs_review") return S.STATUS_NEEDS_REVIEW;
  return S.STATUS_READY;
}

function getStatusColor({ upload_status, masar_status, review_status, inProgress }) {
  if (upload_status === "failed" || masar_status === "failed") return "#D32F2F";
  if (masar_status === "submitted" && review_status === "needs_review") return "#F9A825";
  if (masar_status === "submitted") return "#2E7D32";
  if (inProgress) return "#757575";
  if (review_status === "needs_review") return "#F9A825";
  return "#1976D2";
}

// Distinguish "currently submitting" from "queued in batch" within In Progress.
function getInProgressLabel(uploadId, activeSubmitId) {
  if (uploadId === activeSubmitId) return S.STATUS_IN_PROGRESS;
  return S.STATUS_QUEUED_IN_BATCH;
}
```

- [ ] **Step 2: Commit**

```bash
git add passport-masar-extension/status.js
git commit -m "feat(extension): create status.js — label and color helpers for record state"
```

---

## Task 8: Extension — Create queue-filter.js

**Files:**
- Create: `passport-masar-extension/queue-filter.js`

- [ ] **Step 1: Create queue-filter.js**

```javascript
// Partition records into exactly one of four sections.
// inProgressIds is a Set<number> from chrome.storage.session submission_batch.

function filterQueueSections(records, inProgressIds = new Set()) {
  const pending = [];
  const inProgress = [];
  const submitted = [];
  const failed = [];

  for (const r of records) {
    if (r.upload_status === "failed" || r.masar_status === "failed") {
      failed.push(r);
    } else if (r.masar_status === "submitted") {
      submitted.push(r);
    } else if (r.upload_status === "processed" && !r.masar_status && inProgressIds.has(r.upload_id)) {
      inProgress.push(r);
    } else if (r.upload_status === "processed" && !r.masar_status) {
      pending.push(r);
    }
    // Records with other statuses (e.g. "uploading") are not shown.
  }

  return { pending, inProgress, submitted, failed };
}
```

- [ ] **Step 2: Commit**

```bash
git add passport-masar-extension/queue-filter.js
git commit -m "feat(extension): create queue-filter.js — partition records into 4 tab sections"
```

---

## Task 9: Extension — Create badge.js

**Files:**
- Create: `passport-masar-extension/badge.js`

- [ ] **Step 1: Create badge.js**

```javascript
// Extension badge priority system.
// Priority: 1=session expired (red !) > 2=context change (orange !) > 3=failed count (red N) > 4=clear.

function computeBadgeState({ sessionExpired, contextChangePending, failedCount }) {
  if (sessionExpired) return { text: "!", color: "#D32F2F", priority: 1 };
  if (contextChangePending) return { text: "!", color: "#F57C00", priority: 2 };
  if (failedCount > 0) return { text: String(failedCount), color: "#D32F2F", priority: 3 };
  return { text: "", color: "#000000", priority: 4 };
}

function applyBadge({ text, color }) {
  chrome.action.setBadgeText({ text });
  if (text) {
    chrome.action.setBadgeBackgroundColor({ color });
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add passport-masar-extension/badge.js
git commit -m "feat(extension): create badge.js — priority-based extension badge"
```

---

## Task 10: Extension — Create notifications.js

**Files:**
- Create: `passport-masar-extension/notifications.js`

- [ ] **Step 1: Create notifications.js**

```javascript
// Chrome notification wrapper with 30-second dedup per type.

const NOTIFICATION_TYPES = Object.freeze({
  CONTEXT_CHANGE:  "context_change",
  SESSION_EXPIRED: "session_expired",
  BATCH_COMPLETE:  "batch_complete",
});

const _lastNotified = {};

function notify(type, message, title = S.TOPBAR_TITLE) {
  const now = Date.now();
  if (_lastNotified[type] && now - _lastNotified[type] < 30000) return;
  _lastNotified[type] = now;

  chrome.notifications.create(`masar-${type}-${now}`, {
    type: "basic",
    iconUrl: "icons/icon128.png",
    title,
    message,
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add passport-masar-extension/notifications.js
git commit -m "feat(extension): create notifications.js — deduped Chrome notifications"
```

---

## Task 11: Extension — Create context-change.js

**Files:**
- Create: `passport-masar-extension/context-change.js`

- [ ] **Step 1: Create context-change.js**

```javascript
// Context change detection and submission state machine.

const SUBMISSION_STATES = Object.freeze({
  IDLE: "idle",
  SUBMITTING_CURRENT: "submitting_current",
  QUEUED_MORE: "queued_more",
});

async function detectContextChange({ entity_id, contract_id, auth_token }) {
  const stored = await new Promise((resolve) =>
    chrome.storage.local.get(["masar_entity_id", "masar_contract_id"], resolve)
  );
  if (!stored.masar_entity_id) return null;
  if (entity_id && entity_id !== stored.masar_entity_id) {
    return { reason: "entity_changed" };
  }
  if (contract_id && contract_id !== stored.masar_contract_id) {
    return { reason: "contract_changed" };
  }
  return null;
}

async function applyContextChange() {
  await clearPendingContextChange();
  // The actual values are already updated by webRequest listener or syncSession.
  // Clear group since it belongs to the old context.
  await new Promise((resolve) =>
    chrome.storage.local.remove(
      ["masar_group_id", "masar_group_name", "masar_group_number", "masar_groups_cache"],
      resolve
    )
  );
}

async function hasContextChangePending() {
  const stored = await new Promise((resolve) =>
    chrome.storage.local.get(["pending_context_change"], resolve)
  );
  return !!stored.pending_context_change;
}

async function getContextChangeReason() {
  const stored = await new Promise((resolve) =>
    chrome.storage.local.get(["pending_context_change"], resolve)
  );
  return stored.pending_context_change?.reason || null;
}

async function clearPendingContextChange() {
  await new Promise((resolve) =>
    chrome.storage.local.remove(["pending_context_change"], resolve)
  );
}

function createDebouncedContextChecker(callback, delayMs = 1500) {
  let timer = null;
  return function (...args) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      callback(...args);
    }, delayMs);
  };
}

async function getSubmissionState() {
  const stored = await new Promise((resolve) =>
    chrome.storage.session.get(["submission_state"], resolve)
  );
  return stored.submission_state || SUBMISSION_STATES.IDLE;
}

async function setSubmissionState(state) {
  await new Promise((resolve) =>
    chrome.storage.session.set({ submission_state: state }, resolve)
  );
}

async function shouldStopSubmission() {
  const state = await getSubmissionState();
  // Only continue if we're currently submitting
  return state !== SUBMISSION_STATES.SUBMITTING_CURRENT;
}
```

- [ ] **Step 2: Commit**

```bash
git add passport-masar-extension/context-change.js
git commit -m "feat(extension): create context-change.js — detection, state machine, debounce"
```

---

## Task 12: Extension — Create contract-select.js

**Files:**
- Create: `passport-masar-extension/contract-select.js`

- [ ] **Step 1: Create contract-select.js**

```javascript
// Contract list fetching and selection logic.

async function fetchContracts() {
  const res = await masarFetch(
    "https://masar.nusuk.sa/umrah/contracts_apis/api/ExternalAgent/GetContractList",
    {
      method: "POST",
      body: JSON.stringify({
        umrahCompanyName: null,
        contractStartDate: null,
        contractEndDate: null,
      }),
    }
  );
  if (!res.ok) throw new Error(`GetContractList ${res.status}`);
  const json = await res.json();
  return json.response?.data?.contracts || [];
}

function resolveContractSelection(contracts) {
  const active = contracts.filter((c) => c.contractStatus?.id === 0);
  if (active.length === 0) return { selectedContract: null, showDropdown: false };
  if (active.length === 1) return { selectedContract: active[0], showDropdown: false };
  return { selectedContract: null, showDropdown: true };
}
```

- [ ] **Step 2: Commit**

```bash
git add passport-masar-extension/contract-select.js
git commit -m "feat(extension): create contract-select.js — fetch and resolve active contracts"
```

---

## Task 13: Extension — Rewrite popup.html

**Files:**
- Rewrite: `passport-masar-extension/popup.html`

Reference `docs/final-design-proposal.html` for the implemented popup layout. Current code + spec for behavior.

- [ ] **Step 1: Rewrite popup.html**

```html
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>تسجيل المعتمرين</title>
  <link rel="stylesheet" href="popup.css" />
</head>
<body>
  <!-- Persistent top bar — always visible -->
  <div id="topbar">
    <span id="topbar-title">تسجيل المعتمرين</span>
    <button id="btn-settings" class="icon-btn" title="الإعدادات">&#9881;</button>
  </div>

  <div id="app">
    <!-- Loading -->
    <div id="screen-loading" class="screen hidden">
      <div class="status-banner" style="background:#f0f4ff;border:1px solid #c0d0f0;color:#333;">جارٍ التحميل…</div>
    </div>

    <!-- Error fallback -->
    <div id="screen-error" class="screen hidden">
      <div class="status-banner error">
        <strong>خطأ</strong><br /><span id="error-detail"></span>
      </div>
    </div>

    <!-- Token setup screen -->
    <div id="screen-setup" class="screen hidden">
      <h2>ربط الحساب</h2>
      <label for="api-token-input">رمز الدخول</label>
      <input id="api-token-input" type="password" placeholder="الصق الرمز من أمر /token" />
      <button id="btn-save-token">حفظ</button>
      <div id="setup-error" class="status-banner error hidden"></div>
    </div>

    <!-- Entity IDs not yet captured -->
    <div id="screen-activate" class="screen hidden">
      <div class="status-banner warning">
        افتح <strong>masar.nusuk.sa</strong> في هذا المتصفح للتفعيل.
      </div>
      <button id="btn-open-masar-activate">افتح منصة نسك</button>
    </div>

    <!-- Session expired -->
    <div id="screen-session-expired" class="screen hidden">
      <div id="session-expired-text" class="status-banner error"></div>
      <button id="btn-open-masar-expired"></button>
    </div>

    <!-- Group selection (first launch) -->
    <div id="screen-group-select" class="screen hidden">
      <h2>اختر المجموعة</h2>
      <div id="group-select-hint" class="status-banner warning hidden">
        افتح قائمة المجموعات على منصة نسك — ستظهر هنا تلقائيًا.
      </div>
      <select id="group-select"></select>
      <button id="btn-confirm-group">تأكيد</button>
    </div>

    <!-- Main workspace screen -->
    <div id="screen-main" class="screen hidden">
      <!-- Context-change banner (hidden by default) -->
      <div id="context-change-banner" class="status-banner warning" hidden>
        <span id="ctx-change-reason"></span>
        <div class="ctx-change-actions">
          <button id="ctx-change-confirm" class="small-btn">تحديث</button>
          <button id="ctx-change-defer" class="small-btn secondary">لاحقًا</button>
        </div>
      </div>

      <!-- Home summary: office + contract pill + counts -->
      <div id="home-summary">
        <div class="summary-row">
          <span id="ctx-entity" class="summary-entity">—</span>
        </div>
        <div class="summary-row">
          <div id="contract-dropdown-container" hidden>
            <select id="contract-select" class="contract-dropdown"></select>
          </div>
          <span id="ctx-contract-pill" class="contract-pill">—</span>
        </div>
        <div class="summary-counts">
          <span class="count-badge pending-count-badge"><span id="home-pending-count">0</span> معلّقة</span>
          <span class="count-badge failed-count-badge"><span id="home-failed-count">0</span> فشل</span>
        </div>
      </div>

      <!-- Context panel (collapsible) -->
      <div id="context-panel" class="context-panel">
        <div class="context-row">
          <span class="context-label">الحساب</span>
          <span id="ctx-entity-detail" class="context-value">—</span>
        </div>
        <div class="context-row">
          <span class="context-label">العقد</span>
          <span id="ctx-contract" class="context-value">—</span>
        </div>
        <div class="context-row">
          <span class="context-label">ينتهي</span>
          <span id="ctx-contract-end" class="context-value">—</span>
        </div>
        <div class="context-row">
          <span class="context-label">المجموعة</span>
          <span id="ctx-group" class="context-value">—</span>
        </div>
        <div class="context-footer">
          <span id="ctx-synced" class="context-synced-text">لم يتم التحديث</span>
          <div>
            <button id="btn-change-group" class="icon-btn small" title="تغيير المجموعة">&#8597;</button>
            <button id="btn-refresh-context" class="icon-btn small" title="تحديث البيانات">&#8635;</button>
          </div>
        </div>
      </div>

      <!-- Contract expired / expiring warning -->
      <div id="banner-contract-expired" class="status-banner error" hidden>
        &#9888; انتهى العقد — لن تقبل منصة نسك أي تسجيلات.
      </div>
      <div id="banner-contract-expiring" class="status-banner warning" hidden>
        &#9888; العقد ينتهي اليوم — قد لا تُقبل بعض التسجيلات.
      </div>

      <!-- Tab bar -->
      <div class="tabs">
        <button class="tab active" data-tab="pending">معلّقة <span class="tab-count" id="tab-count-pending">0</span></button>
        <button class="tab" data-tab="in-progress">قيد الرفع <span class="tab-count" id="tab-count-in-progress">0</span></button>
        <button class="tab" data-tab="submitted">تم الرفع <span class="tab-count" id="tab-count-submitted">0</span></button>
        <button class="tab" data-tab="failed">فشل <span class="tab-count" id="tab-count-failed">0</span></button>
      </div>

      <!-- Tab content sections -->
      <div id="pending-section" class="tab-content active">
        <button id="submit-all-btn" class="submit-all-btn" disabled>رفع الكل</button>
        <div id="pending-list" class="record-list"></div>
      </div>

      <div id="in-progress-section" class="tab-content hidden">
        <div id="in-progress-list" class="record-list"></div>
      </div>

      <div id="submitted-section" class="tab-content hidden">
        <div id="submitted-list" class="record-list"></div>
      </div>

      <div id="failed-section" class="tab-content hidden">
        <div id="failed-list" class="record-list"></div>
      </div>

      <!-- Help link -->
      <div class="help-row">
        <a id="help-support-link" href="#" class="help-link">المساعدة</a>
      </div>
    </div>

    <!-- Settings panel -->
    <div id="screen-settings" class="screen hidden">
      <div class="header">
        <button id="btn-back" class="icon-btn" title="رجوع">&rarr;</button>
        <h2>الإعدادات</h2>
      </div>
      <label for="settings-email">البريد الإلكتروني</label>
      <input id="settings-email" type="email" placeholder="agency@example.com" />
      <label for="settings-phone-cc">رمز الدولة</label>
      <input id="settings-phone-cc" type="text" placeholder="966" maxlength="5" />
      <label for="settings-phone">رقم الجوال</label>
      <input id="settings-phone" type="tel" placeholder="5XXXXXXXX" />
      <button id="btn-save-settings">حفظ</button>
      <hr />
      <button id="btn-reset-token" class="danger">إعادة ربط الحساب</button>
    </div>
  </div>

  <script src="config.js"></script>
  <script src="auth.js"></script>
  <script src="popup-failure.js"></script>
  <script src="strings.js"></script>
  <script src="status.js"></script>
  <script src="queue-filter.js"></script>
  <script src="popup.js"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add passport-masar-extension/popup.html
git commit -m "feat(extension): rewrite popup.html — tab bar, context banner, contract dropdown, home summary"
```

---

## Task 14: Extension — Rewrite popup.css

**Files:**
- Rewrite: `passport-masar-extension/popup.css`

Reference `docs/final-design-proposal.html` for visual design (colors, spacing, component styles).

- [ ] **Step 1: Rewrite popup.css**

Keep all existing styles and add new ones. The full file should contain the existing base styles plus:

```css
/* ── Tabs ─────────────────────────────────────────────────────────────── */
.tabs {
  display: flex;
  border-bottom: 2px solid #e8e8e8;
  margin-bottom: 8px;
  gap: 0;
}

.tab {
  flex: 1;
  padding: 8px 4px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  color: #777;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  border-radius: 0;
  transition: color 0.15s, border-color 0.15s;
}
.tab:hover { color: #333; background: transparent; }
.tab.active {
  color: #4a7cf0;
  border-bottom-color: #4a7cf0;
  font-weight: 600;
  background: transparent;
}

.tab-count {
  display: inline-block;
  min-width: 16px;
  height: 16px;
  line-height: 16px;
  text-align: center;
  font-size: 10px;
  font-weight: 600;
  background: #eee;
  color: #555;
  border-radius: 8px;
  padding: 0 4px;
  margin-inline-start: 3px;
}
.tab.active .tab-count {
  background: #4a7cf0;
  color: #fff;
}

.tab-content { display: flex; flex-direction: column; gap: 8px; }
.tab-content.hidden { display: none !important; }

/* ── Submit All ───────────────────────────────────────────────────────── */
.submit-all-btn {
  width: 100%;
  padding: 10px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
}

/* ── Home summary ─────────────────────────────────────────────────────── */
#home-summary {
  background: #f7f8ff;
  border: 1px solid #dde3f8;
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 8px;
}

.summary-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 22px;
}

.summary-entity {
  font-size: 13px;
  font-weight: 600;
  color: #222;
}

.contract-pill {
  display: inline-block;
  font-size: 11px;
  color: #555;
  background: #eef2ff;
  padding: 2px 8px;
  border-radius: 10px;
}

.contract-dropdown {
  font-size: 11px;
  padding: 3px 6px;
  border-radius: 6px;
  border: 1px solid #ddd;
}

.summary-counts {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}

.count-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}
.pending-count-badge {
  background: #e3f2fd;
  color: #1565C0;
}
.failed-count-badge {
  background: #ffebee;
  color: #c62828;
}
.failed-count-badge.zero {
  opacity: 0.4;
}

/* ── Record cards (rich layout) ──────────────────────────────────────── */
.record-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.record-card {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.record-card .record-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.record-card .record-name {
  font-weight: 600;
  font-size: 13px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.record-card .record-meta {
  font-size: 12px;
  color: #777;
}

.record-card .record-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
}

.record-card .record-actions {
  display: flex;
  gap: 6px;
  margin-top: 2px;
}
.record-card .record-actions button {
  flex: 1;
  padding: 6px;
  font-size: 12px;
}

.record-card .status-msg {
  font-size: 12px;
  padding: 3px 0;
}
.record-card .status-msg.success { color: #27ae60; }
.record-card .status-msg.error { color: #e53e3e; }
.record-card .status-msg.loading { color: #4a7cf0; }

/* ── Detail link (submitted cards) ───────────────────────────────────── */
.detail-link {
  font-size: 11px;
  color: #4a7cf0;
  cursor: pointer;
  text-decoration: none;
}
.detail-link:hover { text-decoration: underline; }
.detail-link.muted {
  color: #999;
  cursor: default;
}
.detail-link.muted:hover { text-decoration: none; }

/* ── Context change banner ───────────────────────────────────────────── */
#context-change-banner {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
#context-change-banner[hidden] { display: none !important; }

.ctx-change-actions {
  display: flex;
  gap: 6px;
}
.small-btn {
  padding: 4px 10px;
  font-size: 11px;
  border-radius: 4px;
}

/* ── Spinner for in-progress ─────────────────────────────────────────── */
.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid #ccc;
  border-top-color: #4a7cf0;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-inline-end: 4px;
  vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Help row ────────────────────────────────────────────────────────── */
.help-row {
  text-align: center;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #eee;
}
.help-link {
  font-size: 11px;
  color: #999;
  text-decoration: none;
}
.help-link:hover { color: #4a7cf0; }
```

Preserve all existing styles from the current `popup.css` (base, topbar, app, buttons, context-panel, status-dot, etc.) and append the above. Remove the old `.queue-item` styles (replaced by `.record-card`).

- [ ] **Step 2: Commit**

```bash
git add passport-masar-extension/popup.css
git commit -m "feat(extension): rewrite popup.css — tabs, record cards, badge, context banner, spinner"
```

---

## Task 15: Extension — Rewrite popup.js

**Files:**
- Rewrite: `passport-masar-extension/popup.js`

This is the largest change. Reference `docs/final-design-proposal.html` for the current visual behavior, and the spec for data contracts.

- [ ] **Step 1: Rewrite popup.js**

Full replacement. Key behavioral changes:
- Tab navigation replaces flat queue
- `FETCH_ALL_RECORDS` (limit 200) replaces `FETCH_PENDING`
- `filterQueueSections()` partitions records into 4 tabs
- Submit All → snapshot + `SUBMIT_BATCH` message
- Individual submit → `SUBMIT_RECORD` (no `MARK_REVIEWED` gate)
- Click-to-redirect for submitted cards using `masar_detail_id`
- Context-change banner reads `pending_context_change` from storage
- Contract dropdown from `resolveContractSelection()`
- `chrome.storage.onChanged` listener re-renders on batch state changes

```javascript
// ─── Utilities ────────────────────────────────────────────────────────────────

function $(id) { return document.getElementById(id); }

function showScreen(name) {
  document.querySelectorAll(".screen").forEach((el) => el.classList.add("hidden"));
  const el = $(`screen-${name}`);
  if (el) {
    el.classList.remove("hidden");
  } else {
    console.error("[masar-ext popup] showScreen: no element with id screen-" + name);
  }
}

function showError(msg) {
  $("error-detail").textContent = msg;
  showScreen("error");
}

function showSetupError(msg) {
  const el = $("setup-error");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("hidden", !msg);
}

function showMasarLoginRequired() {
  $("session-expired-text").textContent = S.MASAR_LOGIN_REQUIRED;
  $("btn-open-masar-expired").textContent = S.OPEN_MASAR_BUTTON;
  showScreen("session-expired");
}

async function showRelinkRequired() {
  await storageRemove(["api_token"]);
  showSetupError(S.SETUP_RELINK_REQUIRED);
  showScreen("setup");
}

function storageGet(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
}
function storageSet(data) {
  return new Promise((resolve) => chrome.storage.local.set(data, resolve));
}
function storageRemove(keys) {
  return new Promise((resolve) => chrome.storage.local.remove(keys, resolve));
}
function sessionGet(keys) {
  return new Promise((resolve) => chrome.storage.session.get(keys, resolve));
}

function sendMsg(msg) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      console.error("[masar-ext popup] sendMsg timeout for", msg.type);
      resolve({ ok: false, error: S.ERR_TIMEOUT });
    }, 15000);
    chrome.runtime.sendMessage(msg, (resp) => {
      clearTimeout(timer);
      if (chrome.runtime.lastError) {
        console.error("[masar-ext popup] sendMsg error:", chrome.runtime.lastError.message);
        resolve({ ok: false, error: S.ERR_UNEXPECTED });
        return;
      }
      resolve(resp);
    });
  });
}

// ─── Name helpers ─────────────────────────────────────────────────────────────

function buildDisplayName(record) {
  const d = record.extraction_result?.data;
  if (d) {
    const givenTokens = Array.isArray(d.GivenNameTokensEn) ? d.GivenNameTokensEn : [];
    const given = givenTokens.join(" ");
    const parts = [given, d.SurnameEn].filter(Boolean);
    if (parts.length) return parts.join(" — ");
  }
  return record.passport_number || S.RECORD_FALLBACK(record.upload_id);
}

function buildNationality(record) {
  return record.extraction_result?.data?.CountryCode || "";
}

// ─── Tab management ──────────────────────────────────────────────────────────

let activeTab = "pending";

function switchTab(tabName) {
  activeTab = tabName;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tabName));
  document.querySelectorAll(".tab-content").forEach((s) => {
    s.classList.toggle("hidden", s.id !== `${tabName}-section`);
    s.classList.toggle("active", s.id === `${tabName}-section`);
  });
}

// ─── Rendering ───────────────────────────────────────────────────────────────

let allRecords = [];
let skippedIds = new Set();

async function renderAll() {
  const batch = await sessionGet(["submission_batch", "active_submit_id"]);
  const inProgressIds = new Set(batch.submission_batch || []);
  const activeSubmitId = batch.active_submit_id || null;

  const sections = filterQueueSections(
    allRecords.filter((r) => !skippedIds.has(r.upload_id)),
    inProgressIds
  );

  // Update tab counts
  $("tab-count-pending").textContent = sections.pending.length;
  $("tab-count-in-progress").textContent = sections.inProgress.length;
  $("tab-count-submitted").textContent = sections.submitted.length;
  $("tab-count-failed").textContent = sections.failed.length;

  // Update home summary counts
  $("home-pending-count").textContent = sections.pending.length;
  $("home-failed-count").textContent = sections.failed.length;
  const failedBadge = $("home-failed-count").closest(".failed-count-badge");
  if (failedBadge) failedBadge.classList.toggle("zero", sections.failed.length === 0);

  // Submit All button
  const submitAllBtn = $("submit-all-btn");
  submitAllBtn.textContent = S.ACTION_SUBMIT_ALL(sections.pending.length);
  submitAllBtn.disabled = sections.pending.length === 0;

  // Check contract expired — disable submit buttons
  const contractData = await storageGet(["masar_contract_state"]);
  const contractExpired = contractData.masar_contract_state === "expired";
  if (contractExpired) submitAllBtn.disabled = true;

  // Render each section
  renderPendingList(sections.pending, contractExpired);
  renderInProgressList(sections.inProgress, activeSubmitId);
  renderSubmittedList(sections.submitted);
  renderFailedList(sections.failed);
}

function renderPendingList(records, contractExpired) {
  const list = $("pending-list");
  list.innerHTML = "";
  if (records.length === 0) {
    list.innerHTML = `<div class="empty-state">${S.QUEUE_EMPTY}</div>`;
    return;
  }
  records.forEach((record) => {
    const card = renderPendingCard(document, record, contractExpired);
    list.appendChild(card);
  });
}

function renderPendingCard(doc, record, contractExpired) {
  const card = doc.createElement("div");
  card.className = "record-card";
  card.dataset.id = record.upload_id;

  const statusInfo = {
    upload_status: record.upload_status,
    masar_status: record.masar_status,
    review_status: record.review_status,
    inProgress: false,
  };
  const label = getStatusLabel(statusInfo);
  const color = getStatusColor(statusInfo);

  card.innerHTML = `
    <div class="record-header">
      <span class="record-name">${buildDisplayName(record)}</span>
      <span class="record-badge" style="background:${color}20;color:${color}">${label}</span>
    </div>
    <div class="record-meta">${buildNationality(record)}${record.passport_number ? " · #" + record.passport_number : ""}</div>
    <div class="record-actions">
      <button class="btn-submit">${S.ACTION_SUBMIT}</button>
      <button class="btn-skip secondary">${S.ACTION_SKIP}</button>
    </div>
    <div class="status-msg hidden"></div>
  `;

  const btnSubmit = card.querySelector(".btn-submit");
  if (contractExpired) btnSubmit.disabled = true;
  btnSubmit.addEventListener("click", () => submitSingleRecord(record, card));
  card.querySelector(".btn-skip").addEventListener("click", () => {
    skippedIds.add(record.upload_id);
    renderAll();
  });

  return card;
}

function renderInProgressList(records, activeSubmitId) {
  const list = $("in-progress-list");
  list.innerHTML = "";
  records.forEach((record) => {
    const card = document.createElement("div");
    card.className = "record-card";
    const ipLabel = getInProgressLabel(record.upload_id, activeSubmitId);
    card.innerHTML = `
      <div class="record-header">
        <span class="record-name">${buildDisplayName(record)}</span>
        <span class="record-badge" style="background:#75757520;color:#757575"><span class="spinner"></span>${ipLabel}</span>
      </div>
      <div class="record-meta">${buildNationality(record)}${record.passport_number ? " · #" + record.passport_number : ""}</div>
    `;
    list.appendChild(card);
  });
}

function renderSubmittedList(records) {
  const list = $("submitted-list");
  list.innerHTML = "";
  records.forEach((record) => {
    const card = document.createElement("div");
    card.className = "record-card";
    const statusInfo = {
      upload_status: record.upload_status,
      masar_status: record.masar_status,
      review_status: record.review_status,
      inProgress: false,
    };
    const label = getStatusLabel(statusInfo);
    const color = getStatusColor(statusInfo);

    const hasDetail = !!record.masar_detail_id;
    const detailUrl = hasDetail
      ? `https://masar.nusuk.sa/umrah/mutamer/mutamer-details/${encodeURIComponent(record.masar_detail_id)}`
      : null;
    const linkHtml = hasDetail
      ? `<a class="detail-link" data-url="${detailUrl}">${S.VIEW_DETAILS}</a>`
      : `<span class="detail-link muted">${S.DETAILS_UNAVAILABLE}</span>`;

    card.innerHTML = `
      <div class="record-header">
        <span class="record-name">${buildDisplayName(record)}</span>
        <span class="record-badge" style="background:${color}20;color:${color}">${label}</span>
      </div>
      <div class="record-meta">${buildNationality(record)}${record.passport_number ? " · #" + record.passport_number : ""}</div>
      ${linkHtml}
    `;

    const link = card.querySelector(".detail-link[data-url]");
    if (link) {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        chrome.tabs.create({ url: link.dataset.url });
      });
    }

    list.appendChild(card);
  });
}

function renderFailedList(records) {
  const list = $("failed-list");
  list.innerHTML = "";
  records.forEach((record) => {
    const card = document.createElement("div");
    card.className = "record-card";
    card.innerHTML = `
      <div class="record-header">
        <span class="record-name">${buildDisplayName(record)}</span>
        <span class="record-badge" style="background:#D32F2F20;color:#D32F2F">${S.STATUS_FAILED}</span>
      </div>
      <div class="record-meta">${buildNationality(record)}${record.passport_number ? " · #" + record.passport_number : ""}</div>
      <div class="record-actions">
        <button class="btn-retry">${S.ACTION_RETRY}</button>
      </div>
      <div class="status-msg hidden"></div>
    `;
    card.querySelector(".btn-retry").addEventListener("click", () => submitSingleRecord(record, card));
    list.appendChild(card);
  });
}

// ─── Submit logic ────────────────────────────────────────────────────────────

async function submitSingleRecord(record, card) {
  const btns = card.querySelectorAll("button");
  btns.forEach((b) => (b.disabled = true));
  const statusEl = card.querySelector(".status-msg");
  if (statusEl) {
    statusEl.className = "status-msg loading";
    statusEl.classList.remove("hidden");
    statusEl.textContent = S.STATUS_IN_PROGRESS;
  }

  const res = await sendMsg({ type: "SUBMIT_RECORD", record });

  // Re-fetch all records as source of truth
  await fetchAllRecords();

  if (res && res.ok) {
    if (statusEl) {
      statusEl.className = "status-msg success";
      statusEl.textContent = S.STATUS_SUBMITTED;
    }
    setTimeout(() => renderAll(), 800);
  } else {
    const stillExists = allRecords.some(
      (r) => r.upload_id === record.upload_id && r.masar_status !== "submitted"
    );
    if (!stillExists) {
      if (statusEl) {
        statusEl.className = "status-msg success";
        statusEl.textContent = S.STATUS_SUBMITTED;
      }
      setTimeout(() => renderAll(), 800);
      return;
    }
    const failure = MasarPopupFailure.classifyFailure(res);
    if (failure.type === "relink") { await showRelinkRequired(); return; }
    if (failure.type === "masar-login") { showMasarLoginRequired(); return; }
    if (statusEl) {
      statusEl.className = "status-msg error";
      statusEl.textContent = res?.error || S.ERR_UNEXPECTED;
    }
    btns.forEach((b) => (b.disabled = false));
  }
}

async function submitAll() {
  const batch = await sessionGet(["submission_batch"]);
  const inProgressIds = new Set(batch.submission_batch || []);
  const sections = filterQueueSections(
    allRecords.filter((r) => !skippedIds.has(r.upload_id)),
    inProgressIds
  );
  const pendingIds = sections.pending.map((r) => r.upload_id);
  if (pendingIds.length === 0) return;

  const confirmed = window.confirm(S.SUBMIT_ALL_CONFIRM(pendingIds.length));
  if (!confirmed) return;

  // Snapshot current pending IDs and send batch
  await sendMsg({ type: "SUBMIT_BATCH", uploadIds: pendingIds });
  // renderAll will pick up the storage change via onChanged listener
}

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchAllRecords() {
  const res = await sendMsg({ type: "FETCH_ALL_RECORDS" });
  if (!res || !res.ok) {
    const failure = MasarPopupFailure.classifyFailure(res);
    if (failure.type === "relink") { await showRelinkRequired(); return false; }
    if (failure.type === "masar-login") { showMasarLoginRequired(); return false; }
    return false;
  }
  allRecords = res.data || [];
  return true;
}

// ─── Context panel ───────────────────────────────────────────────────────────

async function populateContextPanel() {
  const data = await storageGet([
    "masar_entity_id", "masar_user_name",
    "masar_contract_id", "masar_contract_number", "masar_contract_name_en",
    "masar_contract_end_date", "masar_contract_state",
    "masar_group_id", "masar_group_name", "masar_group_number",
    "masar_last_synced",
  ]);

  // Home summary entity
  $("ctx-entity").textContent = data.masar_user_name || "—";

  // Context panel detail
  const entityParts = [data.masar_user_name, data.masar_entity_id ? `(${data.masar_entity_id})` : null].filter(Boolean);
  $("ctx-entity-detail").textContent = entityParts.join(" ") || "—";

  // Contract pill (home summary)
  const contractLabel = [data.masar_contract_number ? `#${data.masar_contract_number}` : null, data.masar_contract_name_en].filter(Boolean).join(" · ");
  $("ctx-contract-pill").textContent = contractLabel || (data.masar_contract_id || "—");

  // Contract row (detail)
  $("ctx-contract").textContent = contractLabel || (data.masar_contract_id || "—");

  // Contract end date + state
  const state = data.masar_contract_state || "unknown";
  const endEl = $("ctx-contract-end");
  if (data.masar_contract_end_date) {
    const dateStr = data.masar_contract_end_date.slice(0, 10);
    const labels = { active: S.CONTRACT_ACTIVE, "expires-today": S.CONTRACT_EXPIRES_TODAY, expired: S.CONTRACT_EXPIRED, unknown: "" };
    const label = labels[state] || "";
    endEl.innerHTML = `<span class="status-dot ${state}"></span>${dateStr}${label ? ` · ${label}` : ""}`;
  } else {
    endEl.innerHTML = "—";
  }

  // Group
  const groupParts = [data.masar_group_number, data.masar_group_name].filter(Boolean);
  $("ctx-group").textContent = groupParts.join(" · ") || (data.masar_group_id || "—");

  // Last synced
  if (data.masar_last_synced) {
    const ago = Math.round((Date.now() - data.masar_last_synced) / 1000);
    $("ctx-synced").textContent = ago < 60 ? S.CTX_SYNCED_NOW : S.CTX_SYNCED_AGO(Math.round(ago / 60));
  } else {
    $("ctx-synced").textContent = S.CTX_NOT_SYNCED;
  }

  // Contract banners
  const expiredBanner = $("banner-contract-expired");
  const expiringBanner = $("banner-contract-expiring");
  if (expiredBanner) expiredBanner.hidden = state !== "expired";
  if (expiringBanner) expiringBanner.hidden = state !== "expires-today";
}

// ─── Context change banner ───────────────────────────────────────────────────

async function initContextChangeBanner() {
  const banner = $("context-change-banner");
  const pending = await storageGet(["pending_context_change"]);
  if (!pending.pending_context_change) { banner.hidden = true; return; }

  banner.hidden = false;
  const reason = pending.pending_context_change.reason;
  $("ctx-change-reason").textContent =
    reason === "entity_changed" ? S.CTX_CHANGED_ENTITY : S.CTX_CHANGED_CONTRACT;
}

// ─── Contract dropdown ───────────────────────────────────────────────────────

async function initContractDropdown() {
  try {
    const res = await sendMsg({ type: "FETCH_CONTRACTS" });
    if (!res || !res.ok) return;
    const contracts = res.data || [];
    const { selectedContract, showDropdown } = resolveContractSelection(contracts);
    const container = $("contract-dropdown-container");
    const pill = $("ctx-contract-pill");

    if (showDropdown) {
      container.hidden = false;
      pill.style.display = "none";
      const select = $("contract-select");
      select.innerHTML = "";
      const stored = await storageGet(["masar_contract_id"]);
      const active = contracts.filter((c) => c.contractStatus?.id === 0);
      active.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = String(c.contractId);
        opt.textContent = [c.contractNumber ? `#${c.contractNumber}` : null, c.companyNameEn || c.companyNameAr].filter(Boolean).join(" · ");
        if (String(c.contractId) === stored.masar_contract_id) opt.selected = true;
        select.appendChild(opt);
      });
      select.addEventListener("change", async () => {
        const chosen = active.find((c) => String(c.contractId) === select.value);
        if (!chosen) return;
        await storageSet({
          masar_contract_id: String(chosen.contractId),
          masar_contract_number: chosen.contractNumber || "",
          masar_contract_name_en: chosen.companyNameEn || "",
          masar_contract_name_ar: chosen.companyNameAr || "",
          masar_contract_end_date: chosen.contractEndDate || "",
        });
        populateContextPanel();
      });
    } else if (selectedContract) {
      container.hidden = true;
      pill.style.display = "";
    }
  } catch (e) {
    console.error("[masar-ext popup] initContractDropdown error:", e);
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

async function init() {
  showScreen("loading");

  const stored = await storageGet([
    "api_token", "masar_entity_id", "masar_group_id", "masar_auth_token",
    "agency_email", "agency_phone", "agency_phone_country_code",
  ]);

  if (!stored.api_token) { showSetupError(""); showScreen("setup"); return; }
  if (!stored.masar_entity_id) { showScreen("activate"); return; }

  await sendMsg({ type: "SYNC_SESSION" });

  if (!stored.masar_group_id) {
    const refreshed = await storageGet(["masar_group_id"]);
    if (!refreshed.masar_group_id) { await loadGroupPicker(); return; }
  }

  await loadMainWorkspace();
}

async function loadGroupPicker() {
  showScreen("group-select");
  const res = await sendMsg({ type: "FETCH_GROUPS" });
  const select = $("group-select");
  select.innerHTML = "";

  if (!res || !res.ok) {
    const failure = MasarPopupFailure.classifyFailure(res);
    if (failure.type === "relink") { await showRelinkRequired(); return; }
    if (failure.type === "masar-login") { showMasarLoginRequired(); return; }
    select.innerHTML = `<option value="">${S.GROUP_LOAD_FAILED}</option>`;
    $("group-select-hint").classList.remove("hidden");
    return;
  }
  $("group-select-hint").classList.add("hidden");

  const groups = res.data?.response?.data?.content || [];
  if (groups.length === 0) {
    select.innerHTML = `<option value="">${S.GROUP_NONE_FOUND}</option>`;
    $("group-select-hint").classList.remove("hidden");
    return;
  }
  $("group-select-hint").classList.add("hidden");

  groups.forEach((g) => {
    const opt = document.createElement("option");
    opt.value = g.id;
    opt.dataset.groupName = g.groupName || "";
    opt.dataset.groupNumber = g.groupNumber || "";
    opt.textContent = [g.groupNumber, g.groupName].filter(Boolean).join(" · ") || String(g.id);
    select.appendChild(opt);
  });
}

async function loadMainWorkspace() {
  showScreen("main");
  await populateContextPanel();
  await initContextChangeBanner();
  initContractDropdown(); // fire-and-forget, non-blocking

  const ok = await fetchAllRecords();
  if (!ok) return;

  await renderAll();
}

// ─── Storage change listener (re-render on batch state changes) ──────────────

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "session" && (changes.submission_batch || changes.active_submit_id)) {
    // Batch state changed — re-fetch and re-render
    fetchAllRecords().then((ok) => { if (ok) renderAll(); });
  }
  if (areaName === "local" && changes.pending_context_change) {
    initContextChangeBanner();
  }
});

// ─── Event listeners ─────────────────────────────────────────────────────────

// Tab clicks
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

// Submit All
$("submit-all-btn").addEventListener("click", submitAll);

// Context change banner
$("ctx-change-confirm").addEventListener("click", async () => {
  await sendMsg({ type: "APPLY_CONTEXT_CHANGE" });
  init();
});
$("ctx-change-defer").addEventListener("click", () => {
  $("context-change-banner").hidden = true;
});

// Setup screen
$("btn-save-token").addEventListener("click", async () => {
  const token = $("api-token-input").value.trim();
  const btn = $("btn-save-token");
  if (!token) return;
  showSetupError("");
  btn.disabled = true;
  try {
    const issued = await MasarAuth.exchangeTempToken({
      apiBaseUrl: API_BASE_URL, tempToken: token, fetchImpl: fetch,
    });
    await storageSet({ api_token: issued.sessionToken });
    $("api-token-input").value = "";
    await init();
  } catch (err) {
    showSetupError(S.SETUP_LOGIN_FAILED(err?.message || ""));
  } finally {
    btn.disabled = false;
  }
});

// Activate / session expired
$("btn-open-masar-activate").addEventListener("click", () => sendMsg({ type: "OPEN_MASAR" }));
$("btn-open-masar-expired").addEventListener("click", () => sendMsg({ type: "OPEN_MASAR" }));

// Group picker
$("btn-confirm-group").addEventListener("click", async () => {
  const select = $("group-select");
  const groupId = select.value;
  if (!groupId) return;
  const opt = select.options[select.selectedIndex];
  await storageSet({
    masar_group_id: groupId,
    masar_group_name: opt?.dataset.groupName || "",
    masar_group_number: opt?.dataset.groupNumber || "",
  });
  loadMainWorkspace();
});

// Settings
$("btn-settings").addEventListener("click", async () => {
  const stored = await storageGet(["agency_email", "agency_phone", "agency_phone_country_code"]);
  $("settings-email").value = stored.agency_email || "";
  $("settings-phone-cc").value = stored.agency_phone_country_code || "966";
  $("settings-phone").value = stored.agency_phone || "";
  showScreen("settings");
});
$("btn-back").addEventListener("click", () => init());
$("btn-save-settings").addEventListener("click", async () => {
  await storageSet({
    agency_email: $("settings-email").value.trim(),
    agency_phone_country_code: $("settings-phone-cc").value.trim(),
    agency_phone: $("settings-phone").value.trim(),
  });
  init();
});

$("btn-change-group").addEventListener("click", async () => {
  await storageRemove(["masar_group_id", "masar_group_name", "masar_group_number"]);
  loadGroupPicker();
});

$("btn-refresh-context").addEventListener("click", async () => {
  $("ctx-synced").textContent = S.CTX_SYNCING;
  await sendMsg({ type: "SYNC_SESSION" });
  init();
});

$("btn-reset-token").addEventListener("click", async () => {
  await storageRemove(["api_token", "masar_group_id"]);
  showSetupError("");
  showScreen("setup");
});

// ─── Boot ─────────────────────────────────────────────────────────────────────
init().catch((err) => {
  console.error("[masar-ext popup] init failed:", err);
  showError(err.message || String(err));
});
```

- [ ] **Step 2: Commit**

```bash
git add passport-masar-extension/popup.js
git commit -m "feat(extension): rewrite popup.js — tabbed workspace, batch submit, click-to-redirect, contract dropdown"
```

---

## Task 16: Extension — Update background.js

**Files:**
- Modify: `passport-masar-extension/background.js`

Key changes: add step 7 (GetMutamerList), session-storage batch state, new message handlers (FETCH_ALL_RECORDS, SUBMIT_BATCH, FETCH_CONTRACTS, APPLY_CONTEXT_CHANGE), context-change detection, remove needs_review gate, import new modules.

- [ ] **Step 1: Add importScripts for new modules**

At the top of `background.js`, after existing imports:

```javascript
importScripts("config.js");
importScripts("strings.js");
importScripts("status.js");
importScripts("queue-filter.js");
importScripts("badge.js");
importScripts("notifications.js");
importScripts("context-change.js");
importScripts("contract-select.js");
```

- [ ] **Step 2: Replace updateBadge with new badge system**

Replace the existing `updateBadge(records)` function:

```javascript
async function refreshBadge(records) {
  const sessionExpired = false; // Will be set by context-change detection
  const ctxPending = await hasContextChangePending();
  const failed = records.filter((r) => r.masar_status === "failed" || r.upload_status === "failed").length;
  const state = computeBadgeState({ sessionExpired, contextChangePending: ctxPending, failedCount: failed });
  applyBadge(state);
}
```

Update all calls from `updateBadge(...)` to `refreshBadge(...)`.

- [ ] **Step 3: Add startup reconciliation for session storage**

After the import block, add:

```javascript
// Reconcile stale session storage on service worker startup.
// If no submission is actively running, clear batch state.
chrome.storage.session.get(["submission_batch", "active_submit_id"], (data) => {
  if (data.submission_batch?.length > 0 || data.active_submit_id) {
    log("Startup reconciliation — clearing stale batch state");
    chrome.storage.session.remove(["submission_batch", "active_submit_id"]);
  }
});
```

- [ ] **Step 4: Add debounced context checker to webRequest listener**

Create the debounced checker after the imports, and update the webRequest listener to use it:

```javascript
const debouncedContextCheck = createDebouncedContextChecker(async (headers) => {
  const change = await detectContextChange({
    entity_id: headers.activeentityid,
    contract_id: headers.contractid,
    auth_token: headers.authorization,
  });
  if (change) {
    log("Context change detected:", change.reason);
    await new Promise((resolve) =>
      chrome.storage.local.set({ pending_context_change: change }, resolve)
    );
    notify(NOTIFICATION_TYPES.CONTEXT_CHANGE,
      change.reason === "entity_changed" ? S.CTX_CHANGED_ENTITY : S.CTX_CHANGED_CONTRACT);
    refreshBadge([]);
  }
}, 1500);
```

In the existing `webRequest.onSendHeaders` listener, after `chrome.storage.local.set(update)`, add:

```javascript
      debouncedContextCheck(h);
```

- [ ] **Step 5: Add step 7 (GetMutamerList) to submitToMasar**

After the step 6 success log (`log("submitToMasar — all 6 steps complete!..."`), add step 7:

```javascript
  // ── Step 7: GetMutamerList — fetch Nusuk detail token ────────────────────
  let masar_detail_id = null;
  try {
    const passportNumber = core.PassportNumber || scan.passportNumber;
    log("submitToMasar [7/7] — GetMutamerList, passportNumber:", passportNumber);
    const listRes = await masarFetch(
      "https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/GetMutamerList",
      {
        method: "POST",
        body: JSON.stringify({
          limit: 10, offset: 0, noCount: true,
          sortColumn: null, sortCriteria: [],
          filterList: [{ propertyName: "passportNumber", operation: "match", propertyValue: passportNumber }],
        }),
      }
    );
    if (listRes.ok) {
      const listJson = await listRes.json();
      masar_detail_id = listJson?.response?.data?.content?.[0]?.id ?? null;
      log("submitToMasar [7/7] — masar_detail_id:", masar_detail_id);
    } else {
      log("submitToMasar [7/7] — GetMutamerList failed:", listRes.status, "(non-fatal)");
    }
  } catch (e) {
    logError("submitToMasar [7/7] — error (non-fatal):", e.message);
  }

  log("submitToMasar — all 7 steps complete! mutamerId:", mutamerId, "detailId:", masar_detail_id);
  return { mutamerId, scanResult: scanData, masar_detail_id };
```

- [ ] **Step 6: Update SUBMIT_RECORD handler — remove needs_review gate, add masar_detail_id**

In the `SUBMIT_RECORD` handler, remove the `needs_review` check:

```javascript
  if (msg.type === "SUBMIT_RECORD") {
    const record = msg.record;
    log("SUBMIT_RECORD — upload_id:", record.upload_id);
    return serialiseSubmit(async () => {
    // needs_review gate REMOVED — all processed records can submit directly
    try {
      const { mutamerId, scanResult, masar_detail_id } = await submitToMasar(record);
      const patchRes = await apiFetch(`/records/${record.upload_id}/masar-status`, {
        method: "PATCH",
        body: JSON.stringify({
          status: "submitted",
          masar_mutamer_id: String(mutamerId),
          masar_scan_result: scanResult,
          masar_detail_id: masar_detail_id,
        }),
      });
```

Update the badge refresh after success/failure to use `refreshBadge`:

```javascript
      // Refresh badge after successful submit
      apiFetch("/records?limit=200").then(async (r) => {
        if (r.ok) refreshBadge(await r.json());
      }).catch(() => {});
```

- [ ] **Step 7: Add FETCH_ALL_RECORDS handler**

```javascript
  if (msg.type === "FETCH_ALL_RECORDS") {
    try {
      const res = await apiFetch("/records?limit=200");
      log("FETCH_ALL_RECORDS — status:", res.status);
      if (!res.ok) {
        return { ok: false, status: res.status, failureKind: res.status === 401 ? "backend-auth" : null };
      }
      const data = await res.json();
      log("FETCH_ALL_RECORDS — count:", Array.isArray(data) ? data.length : data);
      refreshBadge(Array.isArray(data) ? data : []);
      return { ok: true, data };
    } catch (err) {
      logError("FETCH_ALL_RECORDS — error:", err.message);
      return { ok: false, error: S.ERR_UNEXPECTED };
    }
  }
```

- [ ] **Step 8: Add SUBMIT_BATCH handler**

```javascript
  if (msg.type === "SUBMIT_BATCH") {
    const uploadIds = msg.uploadIds || [];
    log("SUBMIT_BATCH — ids:", uploadIds);
    // Write batch to session storage
    await new Promise((resolve) =>
      chrome.storage.session.set({ submission_batch: uploadIds, active_submit_id: null }, resolve)
    );
    // Drain sequentially (fire-and-forget — popup watches storage changes)
    drainBatch().catch((err) => logError("SUBMIT_BATCH drain error:", err.message));
    return { ok: true };
  }
```

Add the `drainBatch` function:

```javascript
async function drainBatch() {
  await setSubmissionState(SUBMISSION_STATES.SUBMITTING_CURRENT);
  while (true) {
    const batch = await new Promise((resolve) =>
      chrome.storage.session.get(["submission_batch"], resolve)
    );
    const ids = batch.submission_batch || [];
    if (ids.length === 0) break;

    const uploadId = ids[0];
    // Set active_submit_id
    await new Promise((resolve) =>
      chrome.storage.session.set({ active_submit_id: uploadId }, resolve)
    );

    // Fetch fresh record data from API
    const recordsRes = await apiFetch("/records?limit=200");
    if (!recordsRes.ok) {
      logError("drainBatch — failed to fetch records:", recordsRes.status);
      break;
    }
    const records = await recordsRes.json();
    const record = records.find((r) => r.upload_id === uploadId);

    if (record) {
      try {
        const { mutamerId, scanResult, masar_detail_id } = await submitToMasar(record);
        await apiFetch(`/records/${uploadId}/masar-status`, {
          method: "PATCH",
          body: JSON.stringify({
            status: "submitted",
            masar_mutamer_id: String(mutamerId),
            masar_scan_result: scanResult,
            masar_detail_id: masar_detail_id,
          }),
        });
        log("drainBatch — submitted:", uploadId);
      } catch (err) {
        logError("drainBatch — failed:", uploadId, err.message);
        await apiFetch(`/records/${uploadId}/masar-status`, {
          method: "PATCH",
          body: JSON.stringify({ status: "failed", masar_mutamer_id: null, masar_scan_result: null }),
        }).catch(() => {});
      }
    }

    // Remove from batch
    const updated = await new Promise((resolve) =>
      chrome.storage.session.get(["submission_batch"], resolve)
    );
    const remaining = (updated.submission_batch || []).filter((id) => id !== uploadId);
    await new Promise((resolve) =>
      chrome.storage.session.set({ submission_batch: remaining, active_submit_id: null }, resolve)
    );

    // Check if we should stop (context change detected)
    if (await shouldStopSubmission()) {
      log("drainBatch — stopping due to context change");
      break;
    }
  }

  await setSubmissionState(SUBMISSION_STATES.IDLE);
  await new Promise((resolve) =>
    chrome.storage.session.set({ submission_batch: [], active_submit_id: null }, resolve)
  );

  // Refresh badge and notify
  try {
    const r = await apiFetch("/records?limit=200");
    if (r.ok) refreshBadge(await r.json());
  } catch (_) {}
  notify(NOTIFICATION_TYPES.BATCH_COMPLETE, S.NOTIF_BATCH_COMPLETE);
}
```

- [ ] **Step 9: Add FETCH_CONTRACTS handler**

```javascript
  if (msg.type === "FETCH_CONTRACTS") {
    try {
      const contracts = await fetchContracts();
      return { ok: true, data: contracts };
    } catch (err) {
      logError("FETCH_CONTRACTS — error:", err.message);
      return { ok: false, error: err.message };
    }
  }
```

- [ ] **Step 10: Add APPLY_CONTEXT_CHANGE handler**

```javascript
  if (msg.type === "APPLY_CONTEXT_CHANGE") {
    await applyContextChange();
    refreshBadge([]);
    return { ok: true };
  }
```

- [ ] **Step 11: Commit**

```bash
git add passport-masar-extension/background.js
git commit -m "feat(extension): update background.js — step 7, batch state, context change, FETCH_ALL_RECORDS"
```

---

## Task 17: Extension — Update manifest.json

**Files:**
- Modify: `passport-masar-extension/manifest.json`

- [ ] **Step 1: Add notifications permission**

```json
  "permissions": [
    "cookies",
    "storage",
    "scripting",
    "activeTab",
    "webRequest",
    "notifications"
  ],
```

- [ ] **Step 2: Commit**

```bash
git add passport-masar-extension/manifest.json
git commit -m "feat(extension): add notifications permission to manifest"
```

---

## Task 18: Run full test suite and lint

- [ ] **Step 1: Run all Python tests**

Run: `uv run pytest passport-platform/tests/ passport-api/tests/ passport-core/tests/ passport-telegram/tests/ passport-admin-bot/tests/ passport-benchmark/tests/ -q`
Expected: All PASS.

- [ ] **Step 2: Run linter**

Run: `uv run ruff check passport-admin-bot/src passport-core/src passport-platform/src passport-api/src passport-telegram/src passport-benchmark/src`
Expected: No errors.

- [ ] **Step 3: Run import boundary check**

Run: `uv run lint-imports`
Expected: PASS.

- [ ] **Step 4: Fix any issues found, commit**

If any test or lint failures, fix and commit.

---

## Dependency Graph

```
Task 1 (DB column)
  └─ Task 2 (model/repo/service/schema)
       └─ Task 3 (relax gate)
       └─ Task 4 (API schemas + route)
            └─ Task 5 (API test update)

Task 6 (strings.js)
  └─ Task 7 (status.js)
  └─ Task 8 (queue-filter.js)
  └─ Task 9 (badge.js)
  └─ Task 10 (notifications.js)
  └─ Task 11 (context-change.js)
  └─ Task 12 (contract-select.js)
       └─ Task 13 (popup.html)
       └─ Task 14 (popup.css)
            └─ Task 15 (popup.js) — depends on 7,8,13,14
                 └─ Task 16 (background.js) — depends on 9,10,11,12,15
                      └─ Task 17 (manifest.json)
                           └─ Task 18 (full test + lint)
```

Backend chain (Tasks 1-5) and Extension leaf modules (Tasks 6-12) are independent and can run in parallel.
