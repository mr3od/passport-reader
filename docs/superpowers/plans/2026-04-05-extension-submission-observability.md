# Full Submission Error Dump Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every observed submission failure is durably written into `masar_submissions.submission_error_json` as a full raw dump of the observed error data, response data, and stack trace, and make that same raw JSON string copyable from the popup.

**Architecture:** Keep the existing `masar_submissions` flow and add a single text column named `submission_error_json`. The extension background worker will build one raw JSON string from whatever failure data it actually observes and send that string through the existing `/records/{upload_id}/masar-status` route on every non-success path, while the popup will copy the stored string directly without parsing or reshaping it.
On retry, the extension will first patch the record back to `pending` with `submission_error_json: null`, then start the new submission attempt. On success, the final submitted patch will also send `submission_error_json: null`.

**Tech Stack:** Python workspace (`uv`, FastAPI, SQLite, pytest), Manifest V3 extension (plain JavaScript), existing `passport-platform` records repository/service layers, Node test runner for extension tests.

---

## Guiding Rule

The implementation is built around one rule only:

> We must ensure that we dump the full error, response, and stack trace in the JSON field.

That means:
- do not summarize for storage
- do not parse for storage
- do not reduce the payload to a few selected fields if more raw details are available
- do not create a second diagnostics subsystem
- do not add new persistence tables or support routes

If we observe it during submission, we serialize it into `submission_error_json`.

## File Structure

**New files**
- `passport-platform/migrations/0003_masar_submission_error_json.sql`
  - Reference SQL for adding `submission_error_json` to `masar_submissions`.

**Existing files to modify**
- `passport-platform/src/passport_platform/db.py`
  - Add startup migration for `submission_error_json`.
- `passport-platform/src/passport_platform/models/upload.py`
  - Add `submission_error_json` to `MasarSubmission`.
- `passport-platform/src/passport_platform/schemas/results.py`
  - Add raw `submission_error_json` to `UserRecord`.
- `passport-platform/src/passport_platform/repositories/records.py`
  - Write and read `submission_error_json` as text only.
- `passport-platform/src/passport_platform/services/records.py`
  - Thread `submission_error_json` through the service layer.
- `passport-platform/tests/test_records_service.py`
  - Verify the field is written and returned as-is.
- `passport-api/src/passport_api/schemas.py`
  - Accept and return `submission_error_json` as a string.
- `passport-api/src/passport_api/routes/records.py`
  - Pass `submission_error_json` through the existing PATCH route.
- `passport-api/tests/test_api.py`
  - Verify PATCH and GET record responses include the raw string.
- `passport-masar-extension/background.js`
  - Build one reusable raw JSON string payload and write it on every observed failure path.
- `passport-masar-extension/popup.js`
  - Copy the stored `submission_error_json` string directly from failed rows.
- `passport-masar-extension/strings.js`
  - Add Arabic labels for the copy action.
- `passport-masar-extension/tests/background.test.js`
  - Verify swallowed paths now patch failed state with full raw JSON error dumps.
- `passport-masar-extension/tests/popup.test.js`
  - Verify failed rows render the copy action and copy the stored JSON string.

## Design Rules

- KISS: one new column, one existing route, one popup action.
- YAGNI: no new tables, no event history, no dedicated support API, no backend JSON parsing.
- Reusable: one helper in `background.js` builds the error JSON string; all failure paths call it.
- Maintainable: backend treats the JSON as opaque text and simply stores/returns it.
- Readable: keep the JSON dump builder and popup copy helper as small named functions.
- Easy to debug: store the raw observed data, not a reduced interpretation of it.
- Do not add new summary fields. This change should depend on `submission_error_json`, not on a new summary layer.
- Do not add new derived diagnostic fields such as excerpts, summaries, normalized issue text, or interpreted response fragments.
- Retry resets state: patch `pending` and clear `submission_error_json` before starting the next attempt.
- Success clears stale error data: patch `submitted` with `submission_error_json: null`.

## JSON String Shape

The extension will build a plain object and then call `JSON.stringify(...)` once. The object should be as complete as the observed failure allows.

```json
{
  "source": "masar",
  "stage": "scan_passport",
  "error": {
    "name": "Error",
    "message": "Passport image is not clear",
    "stack": "Error: Passport image is not clear\n    at scanPassportWithFallback ..."
  },
  "http": {
    "status": 400,
    "status_text": "Bad Request"
  },
  "response": {
    "body": "traceError=Passport image is not clear"
  },
  "context": {
    "upload_id": 77,
    "batch_id": "1712345678901-77",
    "contract_id": "224925"
  },
  "at": "2026-04-05T12:30:00Z"
}
```

Rules for the payload:
- `error.message` is the thrown error message if there is one.
- `error.stack` is the full stack trace if there is one.
- `response.body` is the full observed response body if available.
- `http.status` is the observed status code if available.
- Missing data should be `null`, not invented.
- Default to full raw content. Do not truncate in the first implementation.
- Name fields after raw captured data, not inferred meanings.

### Task 1: Add `submission_error_json` to `masar_submissions`

**Files:**
- Create: `passport-platform/migrations/0003_masar_submission_error_json.sql`
- Modify: `passport-platform/src/passport_platform/db.py`
- Modify: `passport-platform/src/passport_platform/models/upload.py`
- Modify: `passport-platform/src/passport_platform/schemas/results.py`
- Modify: `passport-platform/src/passport_platform/repositories/records.py`
- Modify: `passport-platform/src/passport_platform/services/records.py`
- Test: `passport-platform/tests/test_records_service.py`

- [ ] **Step 1: Write the failing records service test**

```python
def test_update_masar_status_stores_submission_error_json(database, records_service, user_factory, upload_factory):
    user = user_factory()
    upload = upload_factory(user_id=user.id)
    error_json = (
        '{"source":"masar","stage":"scan_passport",'
        '"error":{"name":"Error","message":"Passport image is not clear","stack":"Error: Passport image is not clear\\n    at scanPassportWithFallback ..."},'
        '"http":{"status":400,"status_text":"Bad Request"},'
        '"response":{"body":"traceError=Passport image is not clear"},'
        '"context":{"upload_id":77,"batch_id":"batch-77","contract_id":"224925"},'
        '"at":"2026-04-05T12:30:00Z"}'
    )

    updated = records_service.update_masar_status(
        upload_id=upload.id,
        user_id=user.id,
        status="failed",
        masar_mutamer_id=None,
        masar_scan_result=None,
        submission_error_json=error_json,
    )

    assert updated is True
    record = records_service.get_user_record(user.id, upload.id)
    assert record is not None
    assert record.submission_error_json == error_json
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest passport-platform/tests/test_records_service.py::test_update_masar_status_stores_submission_error_json -v`
Expected: FAIL because `submission_error_json` is not accepted or returned.

- [ ] **Step 3: Add the migration and model field**

```sql
ALTER TABLE masar_submissions ADD COLUMN submission_error_json TEXT;
```

```python
@dataclass(slots=True)
class MasarSubmission:
    id: int
    upload_id: int
    status: str
    mutamer_id: str | None
    scan_result_json: str | None
    masar_detail_id: str | None
    submission_entity_id: str | None
    submission_entity_type_id: str | None
    submission_entity_name: str | None
    submission_contract_id: str | None
    submission_contract_name: str | None
    submission_contract_name_ar: str | None
    submission_contract_name_en: str | None
    submission_contract_number: str | None
    submission_contract_status: bool | None
    submission_uo_subscription_status_id: int | None
    submission_group_id: str | None
    submission_group_name: str | None
    submission_group_number: str | None
    submission_error_json: str | None
    failure_reason_code: str | None
    failure_reason_text: str | None
    submitted_at: datetime | None
    created_at: datetime
```

```python
if "submission_error_json" not in masar_columns:
    conn.execute("ALTER TABLE masar_submissions ADD COLUMN submission_error_json TEXT")
```

- [ ] **Step 4: Thread the text field through the repository and service**

```python
def update_masar_status(
    self,
    upload_id: int,
    user_id: int,
    status: str,
    masar_mutamer_id: str | None,
    masar_scan_result: dict | None,
    masar_detail_id: str | None = None,
    submission_entity_id: str | None = None,
    submission_entity_type_id: str | None = None,
    submission_entity_name: str | None = None,
    submission_contract_id: str | None = None,
    submission_contract_name: str | None = None,
    submission_contract_name_ar: str | None = None,
    submission_contract_name_en: str | None = None,
    submission_contract_number: str | None = None,
    submission_contract_status: bool | None = None,
    submission_uo_subscription_status_id: int | None = None,
    submission_group_id: str | None = None,
    submission_group_name: str | None = None,
    submission_group_number: str | None = None,
    submission_error_json: str | None = None,
    failure_reason_code: str | None = None,
    failure_reason_text: str | None = None,
) -> bool:
    masar_scan_result_json = json.dumps(masar_scan_result) if masar_scan_result is not None else None
    return self.records.insert_masar_submission(
        upload_id=upload_id,
        user_id=user_id,
        status=status,
        masar_mutamer_id=masar_mutamer_id,
        masar_scan_result_json=masar_scan_result_json,
        masar_detail_id=masar_detail_id,
        submission_entity_id=submission_entity_id,
        submission_entity_type_id=submission_entity_type_id,
        submission_entity_name=submission_entity_name,
        submission_contract_id=submission_contract_id,
        submission_contract_name=submission_contract_name,
        submission_contract_name_ar=submission_contract_name_ar,
        submission_contract_name_en=submission_contract_name_en,
        submission_contract_number=submission_contract_number,
        submission_contract_status=submission_contract_status,
        submission_uo_subscription_status_id=submission_uo_subscription_status_id,
        submission_group_id=submission_group_id,
        submission_group_name=submission_group_name,
        submission_group_number=submission_group_number,
        submission_error_json=submission_error_json,
        failure_reason_code=failure_reason_code,
        failure_reason_text=failure_reason_text,
    )
```

```python
submission_error_json=row["submission_error_json"],
```

- [ ] **Step 5: Run the records service test**

Run: `uv run pytest passport-platform/tests/test_records_service.py::test_update_masar_status_stores_submission_error_json -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add passport-platform/migrations/0003_masar_submission_error_json.sql passport-platform/src/passport_platform/db.py passport-platform/src/passport_platform/models/upload.py passport-platform/src/passport_platform/schemas/results.py passport-platform/src/passport_platform/repositories/records.py passport-platform/src/passport_platform/services/records.py passport-platform/tests/test_records_service.py
git commit -m "feat: store full submission error dump json on masar submissions [codex]"
```

### Task 2: Expose `submission_error_json` Through the Existing Records API

**Files:**
- Modify: `passport-api/src/passport_api/schemas.py`
- Modify: `passport-api/src/passport_api/routes/records.py`
- Test: `passport-api/tests/test_api.py`

- [ ] **Step 1: Write the failing API test**

```python
def test_patch_masar_status_accepts_submission_error_json(client, auth_headers, processed_record):
    error_json = (
        '{"source":"masar","stage":"scan_passport",'
        '"error":{"name":"Error","message":"Passport image is not clear","stack":"Error: Passport image is not clear\\n    at scanPassportWithFallback ..."},'
        '"http":{"status":400,"status_text":"Bad Request"},'
        '"response":{"body":"traceError=Passport image is not clear"},'
        '"context":{"upload_id":77,"batch_id":"batch-77","contract_id":"224925"},'
        '"at":"2026-04-05T12:30:00Z"}'
    )

    response = client.patch(
        f"/records/{processed_record.upload_id}/masar-status",
        headers=auth_headers,
        json={
            "status": "failed",
            "submission_error_json": error_json,
        },
    )

    assert response.status_code == 200
    assert response.json()["submission_error_json"] == error_json


def test_patch_masar_status_accepts_pending_and_clears_submission_error_json(client, auth_headers, processed_record):
    response = client.patch(
        f"/records/{processed_record.upload_id}/masar-status",
        headers=auth_headers,
        json={
            "status": "pending",
            "submission_error_json": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["masar_status"] == "pending"
    assert response.json()["submission_error_json"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest passport-api/tests/test_api.py -k "submission_error_json or pending_and_clears_submission_error_json" -v`
Expected: FAIL because the API schema rejects or omits `submission_error_json`.

- [ ] **Step 3: Add the request and response schema field**

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
    submission_entity_id: str | None
    submission_entity_type_id: str | None
    submission_entity_name: str | None
    submission_contract_id: str | None
    submission_contract_name: str | None
    submission_contract_name_ar: str | None
    submission_contract_name_en: str | None
    submission_contract_number: str | None
    submission_contract_status: bool | None
    submission_uo_subscription_status_id: int | None
    submission_group_id: str | None
    submission_group_name: str | None
    submission_group_number: str | None
    submission_error_json: str | None
    failure_reason_code: str | None
    failure_reason_text: str | None


class MasarStatusUpdate(BaseModel):
    status: str
    masar_mutamer_id: str | None = None
    masar_scan_result: dict[str, Any] | None = None
    masar_detail_id: str | None = None
    submission_entity_id: str | None = None
    submission_entity_type_id: str | None = None
    submission_entity_name: str | None = None
    submission_contract_id: str | None = None
    submission_contract_name: str | None = None
    submission_contract_name_ar: str | None = None
    submission_contract_name_en: str | None = None
    submission_contract_number: str | None = None
    submission_contract_status: bool | None = None
    submission_uo_subscription_status_id: int | None = None
    submission_group_id: str | None = None
    submission_group_name: str | None = None
    submission_group_number: str | None = None
    submission_error_json: str | None = None
    failure_reason_code: str | None = None
    failure_reason_text: str | None = None
```

- [ ] **Step 4: Pass the field through the route**

```python
if body.status not in ("pending", "submitted", "failed", "missing"):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="status must be 'pending', 'submitted', 'failed', or 'missing'",
    )

updated = services.records.update_masar_status(
    upload_id=upload_id,
    user_id=authenticated.user.id,
    status=body.status,
    masar_mutamer_id=body.masar_mutamer_id,
    masar_scan_result=body.masar_scan_result,
    masar_detail_id=body.masar_detail_id,
    submission_entity_id=body.submission_entity_id,
    submission_entity_type_id=body.submission_entity_type_id,
    submission_entity_name=body.submission_entity_name,
    submission_contract_id=body.submission_contract_id,
    submission_contract_name=body.submission_contract_name,
    submission_contract_name_ar=body.submission_contract_name_ar,
    submission_contract_name_en=body.submission_contract_name_en,
    submission_contract_number=body.submission_contract_number,
    submission_contract_status=body.submission_contract_status,
    submission_uo_subscription_status_id=body.submission_uo_subscription_status_id,
    submission_group_id=body.submission_group_id,
    submission_group_name=body.submission_group_name,
    submission_group_number=body.submission_group_number,
    submission_error_json=body.submission_error_json,
    failure_reason_code=body.failure_reason_code,
    failure_reason_text=body.failure_reason_text,
)
```

```python
submission_error_json=record.submission_error_json,
```

- [ ] **Step 5: Run the API test**

Run: `uv run pytest passport-api/tests/test_api.py -k "submission_error_json or pending_and_clears_submission_error_json" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add passport-api/src/passport_api/schemas.py passport-api/src/passport_api/routes/records.py passport-api/tests/test_api.py
git commit -m "feat: expose full submission error dump json string in records api [codex]"
```

### Task 3: Build One Reusable Full Dump Helper in the Background Worker

**Files:**
- Modify: `passport-masar-extension/background.js`
- Test: `passport-masar-extension/tests/background.test.js`

- [ ] **Step 1: Write the failing helper test**

```javascript
test("background builds a full submission dump json string", () => {
  const payload = buildSubmissionErrorJson({
    source: "masar",
    stage: "scan_passport",
    error: {
      name: "Error",
      message: "Passport image is not clear",
      stack: "Error: Passport image is not clear\n    at scanPassportWithFallback ...",
    },
    http: {
      status: 400,
      statusText: "Bad Request",
    },
    response: {
      body: "traceError=Passport image is not clear",
    },
    context: {
      uploadId: 9,
      batchId: "batch-1",
      contractId: "224925",
    },
  });

  assert.equal(typeof payload, "string");
  assert.equal(payload.includes('"message":"Passport image is not clear"'), true);
  assert.equal(payload.includes('"stack":"Error: Passport image is not clear'), true);
  assert.equal(payload.includes('"body":"traceError=Passport image is not clear"'), true);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test passport-masar-extension/tests/background.test.js`
Expected: FAIL because `buildSubmissionErrorJson` does not exist.

- [ ] **Step 3: Add the reusable full-dump builder**

```javascript
function buildSubmissionErrorJson({
  source = "unknown",
  stage = "unknown",
  error = null,
  http = null,
  response = null,
  context = {},
}) {
  return JSON.stringify({
    source,
    stage,
    error: {
      name: error?.name || null,
      message: error?.message || null,
      stack: error?.stack || null,
    },
    http: {
      status: typeof http?.status === "number" ? http.status : null,
      status_text: http?.statusText || null,
    },
    response: {
      body: response?.body || null,
    },
    context: {
      upload_id: context.uploadId || null,
      batch_id: context.batchId || null,
      contract_id: context.contractId || null,
    },
    at: new Date().toISOString(),
  });
}
```

- [ ] **Step 4: Run the helper test**

Run: `node --test passport-masar-extension/tests/background.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add passport-masar-extension/background.js passport-masar-extension/tests/background.test.js
git commit -m "refactor: add reusable full submission dump helper [codex]"
```

### Task 4: Patch Every Observed Failure Path With the Full Error Dump

**Files:**
- Modify: `passport-masar-extension/background.js`
- Test: `passport-masar-extension/tests/background.test.js`

- [ ] **Step 1: Write the failing swallowed-path tests**

```javascript
test("missing record in batch is patched as failed with full submission_error_json", async () => {
  const patchBodies = [];
  global.fetch = async (url, options = {}) => {
    const text = String(url);
    if (text.endsWith("/records/77")) {
      return { ok: false, status: 404, json: async () => ({ detail: "not found" }) };
    }
    if (text.endsWith("/records/77/masar-status")) {
      patchBodies.push(JSON.parse(options.body));
      return { ok: true, status: 200, json: async () => ({ upload_id: 77, masar_status: "failed" }) };
    }
    if (text.includes("/records/counts")) {
      return { ok: true, status: 200, json: async () => ({ pending: 0, submitted: 0, failed: 1 }) };
    }
    return { ok: true, status: 200, json: async () => ({ items: [], total: 0, has_more: false }) };
  };

  await handleMessage({ type: "SUBMIT_BATCH", uploadIds: [77], sourceTotal: 1, nextOffset: 1 });
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(patchBodies.length, 1);
  assert.equal(patchBodies[0].status, "failed");
  assert.equal(typeof patchBodies[0].submission_error_json, "string");
  assert.equal(patchBodies[0].submission_error_json.includes('"stage":"record_lookup"'), true);
  assert.equal(patchBodies[0].submission_error_json.includes('"message":"Record was not available during batch drain"'), true);
});
```

```javascript
test("caught submission failure is patched with full raw error dump", async () => {
  const error = new Error("Submission failed");
  error.stack = "Error: Submission failed\n    at submitToMasar ...";
  error.failureKind = "masar-auth";
  error.stage = "submit_to_masar";
  error.httpStatus = 401;
  error.responseBody = "Unauthorized";

  const payload = buildSubmissionErrorJson({
    source: "masar",
    stage: error.stage,
    error,
    http: { status: error.httpStatus, statusText: "Unauthorized" },
    response: { body: error.responseBody },
    context: { uploadId: 10, batchId: "batch-10", contractId: "224925" },
  });

  assert.equal(payload.includes('"stack":"Error: Submission failed'), true);
  assert.equal(payload.includes('"body":"Unauthorized"'), true);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test passport-masar-extension/tests/background.test.js`
Expected: FAIL because failure paths do not yet use the full dump helper.

- [ ] **Step 3: Patch missing and ineligible records with the full dump**

```javascript
if (!record) {
  await patchRecordStatus(uploadId, {
    status: "failed",
    masar_mutamer_id: null,
    masar_scan_result: null,
    masar_detail_id: null,
    submission_error_json: buildSubmissionErrorJson({
      source: "extension",
      stage: "record_lookup",
      error: {
        name: "RecordLookupError",
        message: "Record was not available during batch drain",
        stack: null,
      },
      http: null,
      response: {
        body: "record lookup returned 404 or no payload",
      },
      context: {
        uploadId,
        batchId: batch.batch_id,
        contractId: submissionContext.submission_contract_id,
      },
    }),
    ...submissionContext,
  }).catch(() => {});
  batch = advanceSubmissionBatch(batch, uploadId, { status: "failed" });
  await persistSubmissionBatch(batch);
  continue;
}
```

```javascript
if (!shouldSubmitRecord(record)) {
  await patchRecordStatus(uploadId, {
    status: "failed",
    masar_mutamer_id: null,
    masar_scan_result: null,
    masar_detail_id: null,
    submission_error_json: buildSubmissionErrorJson({
      source: "extension",
      stage: "submission_gate",
      error: {
        name: "SubmissionGateError",
        message: "Record was not eligible for submission",
        stack: null,
      },
      http: null,
      response: {
        body: JSON.stringify({
          upload_status: record.upload_status || null,
          masar_status: record.masar_status || null,
        }),
      },
      context: {
        uploadId,
        batchId: batch.batch_id,
        contractId: submissionContext.submission_contract_id,
      },
    }),
    ...submissionContext,
  }).catch(() => {});
  batch = advanceSubmissionBatch(batch, uploadId, { status: "failed" });
  await persistSubmissionBatch(batch);
  continue;
}
```

- [ ] **Step 4: Patch caught submission failures with the full dump**

```javascript
const submissionErrorJson = buildSubmissionErrorJson({
  source: error.failureKind === "backend-auth"
    ? "api"
    : error.failureKind === "masar-auth"
      ? "masar"
      : "extension",
  stage: error.stage || "submit_to_masar",
  error,
  http: {
    status: error.httpStatus || null,
    statusText: error.httpStatus ? String(error.httpStatus) : null,
  },
  response: {
    body: error.responseExcerpt || null,
  },
  context: {
    uploadId: record.upload_id,
    batchId: batchRequestContext.started_at ? String(batchRequestContext.started_at) : null,
    contractId: submissionContext.submission_contract_id,
  },
});

await patchRecordStatus(record.upload_id, {
  status: "failed",
  masar_mutamer_id: null,
  masar_scan_result: null,
  masar_detail_id: null,
  submission_error_json: submissionErrorJson,
  ...submissionContext,
});
```

- [ ] **Step 5: Clear stale error data on success**

```javascript
await patchRecordStatus(record.upload_id, {
  status: "submitted",
  masar_mutamer_id: String(mutamerId),
  masar_scan_result: scanResult,
  masar_detail_id: masarDetailId ? String(masarDetailId) : null,
  submission_error_json: null,
  ...submissionContext,
});
```

- [ ] **Step 6: Run the background tests**

Run: `node --test passport-masar-extension/tests/background.test.js`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add passport-masar-extension/background.js passport-masar-extension/tests/background.test.js
git commit -m "fix: dump full observed submission failures into json string [codex]"
```

### Task 5: Add Retry Reset Support in the Background Worker

**Files:**
- Modify: `passport-masar-extension/background.js`
- Test: `passport-masar-extension/tests/background.test.js`

- [ ] **Step 1: Write the failing retry-reset test**

```javascript
test("retry reset patches record back to pending and clears submission_error_json", async () => {
  const patchBodies = [];
  global.fetch = async (url, options = {}) => {
    const text = String(url);
    if (text.endsWith("/records/18/masar-status")) {
      patchBodies.push(JSON.parse(options.body));
      return { ok: true, status: 200, json: async () => ({ upload_id: 18, masar_status: "pending" }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  };

  const response = await handleMessage({ type: "PATCH_RECORD_PENDING_FOR_RETRY", uploadId: 18 });

  assert.equal(response.ok, true);
  assert.equal(patchBodies.length, 1);
  assert.equal(patchBodies[0].status, "pending");
  assert.equal(patchBodies[0].submission_error_json, null);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test passport-masar-extension/tests/background.test.js`
Expected: FAIL because the message type does not exist.

- [ ] **Step 3: Add the background retry-reset message**

```javascript
if (msg.type === "PATCH_RECORD_PENDING_FOR_RETRY") {
  await patchRecordStatus(msg.uploadId, {
    status: "pending",
    masar_mutamer_id: null,
    masar_scan_result: null,
    masar_detail_id: null,
    submission_error_json: null,
    failure_reason_code: null,
    failure_reason_text: null,
  });
  return { ok: true };
}
```

- [ ] **Step 4: Run the background tests**

Run: `node --test passport-masar-extension/tests/background.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add passport-masar-extension/background.js passport-masar-extension/tests/background.test.js
git commit -m "feat: reset retry state to pending before resubmission [codex]"
```

### Task 6: Preserve Full Raw Response and Stack Trace When Errors Are Created

**Files:**
- Modify: `passport-masar-extension/background.js`
- Test: `passport-masar-extension/tests/background.test.js`

- [ ] **Step 1: Write the failing metadata test**

```javascript
test("observed error metadata is attached before catch-time json dump", () => {
  const error = taggedError("scan-image-unclear", "Passport image is not clear", {
    stage: "scan_passport",
    httpStatus: 400,
    responseBody: "traceError=Passport image is not clear",
    httpStatusText: "Bad Request",
  });

  assert.equal(error.stage, "scan_passport");
  assert.equal(error.httpStatus, 400);
  assert.equal(error.responseBody, "traceError=Passport image is not clear");
  assert.equal(error.httpStatusText, "Bad Request");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test passport-masar-extension/tests/background.test.js`
Expected: FAIL if observed metadata is not attached consistently.

- [ ] **Step 3: Attach full observed metadata where errors are thrown**

```javascript
throw taggedError(
  failureKind,
  failureKind === "scan-image-unclear" ? S.ERR_SCAN_IMAGE_UNCLEAR : S.ERR_CONTRACT_NOT_ACTIVE,
  {
    stage: "scan_passport",
    httpStatus: response.status,
    httpStatusText: response.statusText || null,
    responseBody: traceError || errorBody || null,
    failureReason: buildFailureReason(failureKind, traceError),
  },
);
```

```javascript
throw taggedError(
  step4Res.status === 401 ? "masar-auth" : null,
  S.ERR_UPLOAD_ATTACH(step4Res.status),
  {
    stage: "attachment_upload",
    httpStatus: step4Res.status,
    httpStatusText: step4Res.statusText || null,
    responseBody: errText,
  },
);
```

- [ ] **Step 4: Use raw HTTP and response fields in the dump helper calls**

```javascript
http: {
  status: error.httpStatus || null,
  statusText: error.httpStatusText || null,
},
response: {
  body: error.responseBody || null,
},
```

- [ ] **Step 5: Run the background tests**

Run: `node --test passport-masar-extension/tests/background.test.js`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add passport-masar-extension/background.js passport-masar-extension/tests/background.test.js
git commit -m "refactor: preserve full observed response and stack metadata [codex]"
```

### Task 7: Add a Simple Failed-Row Copy Action in the Popup

**Files:**
- Modify: `passport-masar-extension/popup.js`
- Modify: `passport-masar-extension/strings.js`
- Test: `passport-masar-extension/tests/popup.test.js`

- [ ] **Step 1: Write the failing popup test**

```javascript
test("failed record renders copy dump action using stored submission_error_json", async () => {
  const copied = [];
  global.navigator = {
    clipboard: {
      writeText: async (value) => copied.push(value),
    },
  };

  const record = {
    upload_id: 12,
    passport_number: "A1234567",
    masar_status: "failed",
    submission_error_json:
      '{"source":"masar","stage":"scan_passport","error":{"name":"Error","message":"Passport image is not clear","stack":"Error: Passport image is not clear\\n    at scanPassportWithFallback ..."},"http":{"status":400,"status_text":"Bad Request"},"response":{"body":"traceError=Passport image is not clear"},"context":{"upload_id":12,"batch_id":"batch-12","contract_id":"224925"},"at":"2026-04-05T12:30:00Z"}',
    _onRetry: async () => {},
  };

  const card = renderPendingCard(documentStub, { ...record, _section: "failed" });
  await card.querySelector(".copy-dump-btn").click();

  assert.equal(copied.length, 1);
  assert.equal(copied[0], record.submission_error_json);
});


test("retry resets row to pending before starting a new submission", async () => {
  const messages = [];
  global.chrome = {
    runtime: {
      sendMessage: (message, callback) => {
        messages.push(message);
        callback({ ok: true });
      },
    },
  };

  const record = {
    upload_id: 18,
    masar_status: "failed",
    submission_error_json: '{"error":{"message":"boom"}}',
    _onRetry: async () => {},
  };

  await submitSingle(record);

  assert.equal(messages.some((message) => (
    message.type === "PATCH_RECORD_PENDING_FOR_RETRY" && message.uploadId === 18
  )), true);
  delete global.chrome;
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test passport-masar-extension/tests/popup.test.js`
Expected: FAIL because no copy button exists.

- [ ] **Step 3: Add Arabic strings**

```javascript
ACTION_COPY_DUMP: "نسخ الخطأ",
COPY_DUMP_SUCCESS: "تم نسخ الخطأ",
COPY_DUMP_FAILED: "تعذر نسخ الخطأ",
```

- [ ] **Step 4: Add a small copy helper and failed-row action**

```javascript
function getErrorDumpText(record) {
  return typeof record.submission_error_json === "string" && record.submission_error_json.trim()
    ? record.submission_error_json
    : "";
}
```

```javascript
async function resetRecordForRetry(uploadId) {
  return sendMsg({
    type: "PATCH_RECORD_PENDING_FOR_RETRY",
    uploadId,
  }, { timeoutMs: 15000 });
}
```

```javascript
actions.append(
  createActionButton(doc, Strings.ACTION_COPY_DUMP, async () => {
    const dumpText = getErrorDumpText(record);
    try {
      await navigator.clipboard.writeText(dumpText);
      showToast(Strings.COPY_DUMP_SUCCESS, { tone: "neutral" });
    } catch {
      showToast(Strings.COPY_DUMP_FAILED, { tone: "error" });
    }
  }, {
    className: "ghost-btn copy-dump-btn",
    disabled: !getErrorDumpText(record),
  }),
  createActionButton(doc, Strings.ACTION_RETRY, async () => {
    await resetRecordForRetry(record.upload_id);
    await record._onRetry();
  }, {
    disabled: Boolean(record._submitDisabled),
  }),
);
```

- [ ] **Step 5: Run the popup tests**

Run: `node --test passport-masar-extension/tests/popup.test.js`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add passport-masar-extension/popup.js passport-masar-extension/strings.js passport-masar-extension/tests/popup.test.js
git commit -m "feat: add popup copy action for full dump json string [codex]"
```

### Task 8: Verify the Minimal Change Set

**Files:**
- Modify: `docs/HISTORY.md`

- [ ] **Step 1: Run Python lint**

Run: `uv run ruff check passport-platform passport-api`
Expected: PASS.

- [ ] **Step 2: Run Python format**

Run: `uv run ruff format passport-platform passport-api`
Expected: PASS or formatting changes applied.

- [ ] **Step 3: Run import boundary checks**

Run: `uv run lint-imports`
Expected: PASS.

- [ ] **Step 4: Run type checks**

Run: `uv run ty check passport-platform passport-api`
Expected: PASS.

- [ ] **Step 5: Run Python tests**

Run: `uv run pytest passport-platform/tests/test_records_service.py passport-api/tests/test_api.py -v`
Expected: PASS.

- [ ] **Step 6: Run extension tests**

Run: `node --test passport-masar-extension/tests/background.test.js passport-masar-extension/tests/popup.test.js`
Expected: PASS.

- [ ] **Step 7: Update history**

```markdown
- Stored full observed submission failure dumps in `masar_submissions.submission_error_json`, removed silent swallowed submission paths, and added failed-row dump copy support in the extension popup. Authored by codex.
```

- [ ] **Step 8: Commit**

```bash
git add docs/HISTORY.md
git commit -m "docs: record full submission error dump work [codex]"
```

## Self-Review

**Spec coverage**
- Existing `masar_submissions` flow only: covered in Task 1 and Task 2.
- Dump full observed error, response, and stack trace in the JSON field: covered in Task 3, Task 4, and Task 5.
- Prevent swallowed records: covered in Task 4.
- Retry resets state to `pending` and clears old error dumps: covered in Task 2 and Task 6.
- Agencies can copy the exact stored dump directly: covered in Task 6.
- No new summary fields: covered by the design rules and by all patch examples using `submission_error_json` directly.
- Keep the implementation simple: covered by one new column, one existing route, one reusable builder, and one popup copy helper.

**Placeholder scan**
- No `TBD`, `TODO`, or deferred implementation notes remain.
- Every code step includes concrete code and exact commands.

**Type consistency**
- `submission_error_json` is the DB, service, API, and popup field name everywhere.
- `buildSubmissionErrorJson` and `getErrorDumpText` are the only new helper names used across later tasks.

Plan complete and saved to `docs/superpowers/plans/2026-04-05-extension-submission-observability.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
