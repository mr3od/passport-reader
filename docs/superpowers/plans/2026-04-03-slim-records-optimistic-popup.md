# Slim Records And Optimistic Popup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the heavy `/records` list contract with a slim extension-only API, move the popup to per-tab paginated data with optimistic bulk-submit state, and redesign passport cards for a lower-cognitive-load workspace.

**Architecture:** Keep `GET /records/{upload_id}` as the only heavy detail endpoint. Add separate lightweight platform DTOs and repository queries for list, counts, and submit-eligible IDs, then update the extension background and popup to consume those endpoints with local optimistic merge state in `chrome.storage.session`.

**Tech Stack:** FastAPI, Pydantic, SQLite, Python services/repositories, Chrome extension JavaScript, Jest, `uv`, `ruff`, `ty`, `pytest`

---

## File Map

**API**
- Modify: `passport-api/src/passport_api/schemas.py`
- Modify: `passport-api/src/passport_api/routes/records.py`
- Modify: `passport-api/tests/test_api.py`
- Modify: `passport-api/README.md`

**Platform**
- Modify: `passport-platform/src/passport_platform/schemas/results.py`
- Modify: `passport-platform/src/passport_platform/repositories/records.py`
- Modify: `passport-platform/src/passport_platform/services/records.py`
- Modify: `passport-platform/src/passport_platform/db.py`
- Modify: `passport-platform/migrations/`
- Modify: `passport-platform/tests/test_records_service.py`
- Modify: `passport-platform/README.md`

**Extension**
- Modify: `passport-masar-extension/background.js`
- Modify: `passport-masar-extension/popup.js`
- Modify: `passport-masar-extension/queue-filter.js`
- Modify: `passport-masar-extension/strings.js`
- Modify: `passport-masar-extension/tests/background.test.js`
- Modify: `passport-masar-extension/tests/popup.test.js`
- Modify: `passport-masar-extension/tests/queue-filter.test.js`
- Modify: `passport-masar-extension/tests/popup-failure.test.js`
- Modify: `docs/EXTENSION.md`

## Task 1: Lock The Slim API Contract In Tests

**Files:**
- Modify: `passport-api/tests/test_api.py`
- Reference: `passport-api/src/passport_api/schemas.py`
- Reference: `passport-api/src/passport_api/routes/records.py`

- [ ] **Step 1: Write failing API tests for the new list, counts, ids, and heavy-detail boundary**

```python
def test_records_list_returns_paginated_slim_payload(client, session_token):
    response = client.get(
        "/records?section=pending&limit=50&offset=0",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    payload = response.json()
    assert response.status_code == 200
    assert set(payload.keys()) == {"items", "limit", "offset", "total", "has_more"}
    assert "extraction_result" not in payload["items"][0]
    assert "passport_image_uri" not in payload["items"][0]


def test_records_counts_returns_server_truth(client, session_token):
    response = client.get("/records/counts", headers={"Authorization": f"Bearer {session_token}"})
    assert response.status_code == 200
    assert set(response.json().keys()) == {"pending", "submitted", "failed"}


def test_records_ids_returns_submit_eligible_rows_only(client, session_token):
    response = client.get(
        "/records/ids?section=pending&limit=100&offset=0",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    payload = response.json()
    assert response.status_code == 200
    assert set(payload["items"][0].keys()) == {
        "upload_id",
        "upload_status",
        "review_status",
        "masar_status",
    }


def test_record_detail_still_returns_heavy_fields(client, session_token, upload):
    response = client.get(
        f"/records/{upload.id}",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    payload = response.json()
    assert response.status_code == 200
    assert "extraction_result" in payload
    assert "passport_image_uri" in payload
```

- [ ] **Step 2: Run the targeted API tests to verify failure**

Run: `uv run pytest passport-api/tests/test_api.py -q`

Expected: failures for missing routes, wrong response shape, and old `/records` list contract.

- [ ] **Step 3: Add explicit tests for pagination validation and limit enforcement**

```python
def test_records_list_rejects_oversize_limit(client, session_token):
    response = client.get(
        "/records?section=all&limit=101&offset=0",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert response.status_code == 422


def test_records_list_uses_has_more_and_total(client, session_token):
    response = client.get(
        "/records?section=all&limit=1&offset=0",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    payload = response.json()
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert isinstance(payload["total"], int)
    assert isinstance(payload["has_more"], bool)
```

Note: `section=all` is valid for `GET /records` only. `GET /records/ids` remains `section=pending` only. Seed the test fixtures with at least one pending, submitted, and failed record so `section=all` exercises mixed-section pagination instead of a single-state dataset.

- [ ] **Step 4: Re-run the same API test file and confirm only contract-related failures remain**

Run: `uv run pytest passport-api/tests/test_api.py -q`

Expected: FAIL, but only for the new slim-records expectations.

- [ ] **Step 5: Commit the test-first checkpoint**

```bash
git add passport-api/tests/test_api.py
git commit -m "test: define slim records api contract [codex]"
```

## Task 2: Add Lightweight Platform DTOs And Repository Queries

**Files:**
- Modify: `passport-platform/src/passport_platform/schemas/results.py`
- Modify: `passport-platform/src/passport_platform/repositories/records.py`
- Modify: `passport-platform/src/passport_platform/services/records.py`
- Modify: `passport-platform/tests/test_records_service.py`

- [ ] **Step 1: Write failing platform tests for slim list projection, counts, and eligible ids**

```python
def test_list_user_record_items_returns_slim_names(records_service, user):
    items = records_service.list_user_record_items(user.id, limit=50, offset=0, section="pending")
    assert items
    assert items[0].full_name_ar is not None or items[0].full_name_en is not None


def test_count_user_record_sections_returns_pending_submitted_failed(records_service, user):
    counts = records_service.count_user_record_sections(user.id)
    assert counts.pending >= 0
    assert counts.submitted >= 0
    assert counts.failed >= 0


def test_list_submit_eligible_record_ids_excludes_review_blocked_records(records_service, user):
    items = records_service.list_submit_eligible_record_ids(user.id, limit=100, offset=0)
    assert all(item.review_status != "needs_review" for item in items.items)
```

- [ ] **Step 2: Run the targeted platform tests to verify the new methods do not exist yet**

Run: `uv run pytest passport-platform/tests/test_records_service.py -q`

Expected: FAIL with missing service/repository methods and missing DTO types.

- [ ] **Step 3: Add lightweight DTOs in `results.py`**

```python
@dataclass(slots=True)
class UserRecordListItem:
    upload_id: int
    filename: str
    upload_status: UploadStatus
    review_status: str | None
    masar_status: str | None
    masar_detail_id: str | None
    passport_number: str | None
    full_name_ar: str | None
    full_name_en: str | None
    created_at: datetime
    completed_at: datetime | None
    failure_reason_code: str | None
    failure_reason_text: str | None


@dataclass(slots=True)
class UserRecordCounts:
    pending: int
    submitted: int
    failed: int


@dataclass(slots=True)
class UserRecordIdItem:
    upload_id: int
    upload_status: UploadStatus
    review_status: str | None
    masar_status: str | None


@dataclass(slots=True)
class UserRecordListResult:
    items: list[UserRecordListItem]
    total: int
    has_more: bool


@dataclass(slots=True)
class UserRecordIdListResult:
    items: list[UserRecordIdItem]
    total: int
    has_more: bool
```

- [ ] **Step 4: Add dedicated repository queries instead of reusing `_USER_RECORD_COLUMNS`**

```python
def list_user_record_items(self, user_id: int, *, limit: int, offset: int, section: str):
    rows = conn.execute(
        f"""
        SELECT
            uploads.id AS upload_id,
            uploads.filename AS filename,
            uploads.status AS upload_status,
            uploads.created_at AS created_at,
            processing_results.completed_at AS completed_at,
            processing_results.review_status AS review_status,
            processing_results.passport_number AS passport_number,
            processing_results.extraction_result_json AS extraction_result_json,
            ms.masar_status AS masar_status,
            ms.masar_detail_id AS masar_detail_id,
            ms.failure_reason_code AS failure_reason_code,
            ms.failure_reason_text AS failure_reason_text
        FROM uploads
        LEFT JOIN processing_results ON processing_results.upload_id = uploads.id
        {_LATEST_MASAR_SUBMISSION_JOIN}
        WHERE uploads.user_id = ?
        {section_sql}
        ORDER BY uploads.created_at DESC, uploads.id DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, limit, offset),
    ).fetchall()
```

- [ ] **Step 5: Parse names centrally from extraction JSON in the repository mapper and keep the DTO boundary explicit**

```python
def _list_item_names(extraction_result_json: str | None) -> tuple[str | None, str | None]:
    extraction = _parse_json(extraction_result_json)
    data = extraction.get("data") if isinstance(extraction, dict) else None
    if not isinstance(data, dict):
        return None, None
    return _join_name_tokens(data, "GivenNameTokensAr", "SurnameAr"), _join_name_tokens(
        data,
        "GivenNameTokensEn",
        "SurnameEn",
    )


def _row_to_user_record_list_item(row) -> UserRecordListItem:
    full_name_ar, full_name_en = _list_item_names(row["extraction_result_json"])
    return UserRecordListItem(
        upload_id=int(row["upload_id"]),
        filename=row["filename"],
        upload_status=UploadStatus(row["upload_status"]),
        review_status=row["review_status"],
        masar_status=row["masar_status"],
        masar_detail_id=row["masar_detail_id"],
        passport_number=row["passport_number"],
        full_name_ar=full_name_ar,
        full_name_en=full_name_en,
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=...,
        failure_reason_code=row["failure_reason_code"],
        failure_reason_text=row["failure_reason_text"],
    )
```

`extraction_result_json` may be selected inside the repository query only long enough to compute `full_name_ar` and `full_name_en`. It must never be assigned to any lightweight DTO or API schema.

- [ ] **Step 6: Add total and has-more computation in the repository layer**

```python
total = conn.execute(
    f"""
    SELECT COUNT(*)
    FROM uploads
    LEFT JOIN processing_results ON processing_results.upload_id = uploads.id
    {_LATEST_MASAR_SUBMISSION_JOIN}
    WHERE uploads.user_id = ?
    {section_sql}
    """,
    (user_id,),
).fetchone()[0]

return UserRecordListResult(
    items=[_row_to_user_record_list_item(row) for row in rows],
    total=int(total),
    has_more=offset + len(rows) < int(total),
)
```

- [ ] **Step 7: Add service wrappers with the new method names**

```python
def list_user_record_items(self, user_id: int, *, limit: int, offset: int, section: str):
    return self.records.list_user_record_items(user_id, limit=limit, offset=offset, section=section)


def count_user_record_sections(self, user_id: int):
    return self.records.count_user_record_sections(user_id)


def list_submit_eligible_record_ids(self, user_id: int, *, limit: int, offset: int):
    return self.records.list_submit_eligible_record_ids(user_id, limit=limit, offset=offset)
```

- [ ] **Step 8: Re-run the targeted platform tests**

Run: `uv run pytest passport-platform/tests/test_records_service.py -q`

Expected: PASS for new slim DTO/query behavior.

- [ ] **Step 9: Commit the platform boundary split**

```bash
git add passport-platform/src/passport_platform/schemas/results.py passport-platform/src/passport_platform/repositories/records.py passport-platform/src/passport_platform/services/records.py passport-platform/tests/test_records_service.py
git commit -m "feat: add slim record platform queries [codex]"
```

## Task 3: Replace The Records API List Surface

**Files:**
- Modify: `passport-api/src/passport_api/schemas.py`
- Modify: `passport-api/src/passport_api/routes/records.py`
- Modify: `passport-api/tests/test_api.py`

- [ ] **Step 1: Add the new API response models**

```python
class RecordListItemResponse(BaseModel):
    upload_id: int
    filename: str
    upload_status: str
    review_status: str | None
    masar_status: str | None
    masar_detail_id: str | None
    passport_number: str | None
    full_name_ar: str | None
    full_name_en: str | None
    created_at: datetime
    completed_at: datetime | None
    failure_reason_code: str | None
    failure_reason_text: str | None


class RecordListResponse(BaseModel):
    items: list[RecordListItemResponse]
    limit: int
    offset: int
    total: int
    has_more: bool
```

- [ ] **Step 2: Change `GET /records` to the slim paginated response**

```python
@router.get("/records", response_model=RecordListResponse)
def list_records(..., section: str = Query(default="pending", pattern="^(pending|submitted|failed|all)$"), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> RecordListResponse:
    result = services.records.list_user_record_items(
        authenticated.user.id,
        limit=limit,
        offset=offset,
        section=section,
    )
    return RecordListResponse(
        items=[_list_item_to_response(item) for item in result.items],
        limit=limit,
        offset=offset,
        total=result.total,
        has_more=result.has_more,
    )
```

Register `/records/counts` and `/records/ids` before `/records/{upload_id}` in this file. Do not rely on FastAPI path coercion to disambiguate static routes from `{upload_id}`.

- [ ] **Step 3: Add `GET /records/counts` and `GET /records/ids`**

```python
@router.get("/records/counts", response_model=RecordCountsResponse)
def get_record_counts(...):
    counts = services.records.count_user_record_sections(authenticated.user.id)
    return RecordCountsResponse(
        pending=counts.pending,
        submitted=counts.submitted,
        failed=counts.failed,
    )


@router.get("/records/ids", response_model=RecordIdListResponse)
def list_record_ids(..., section: str = Query(default="pending", pattern="^pending$"), limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    result = services.records.list_submit_eligible_record_ids(
        authenticated.user.id,
        limit=limit,
        offset=offset,
    )
    return RecordIdListResponse(...)
```

- [ ] **Step 4: Keep `GET /records/{upload_id}` unchanged as the heavy detail endpoint**

```python
@router.get("/records/{upload_id}", response_model=RecordResponse)
def get_record(...):
    ...
```

- [ ] **Step 5: Run the API tests for the new route behavior**

Run: `uv run pytest passport-api/tests/test_api.py -q`

Expected: PASS for list/counts/ids/detail contract tests.

- [ ] **Step 6: Commit the API contract flip**

```bash
git add passport-api/src/passport_api/schemas.py passport-api/src/passport_api/routes/records.py passport-api/tests/test_api.py
git commit -m "feat: expose slim records list api [codex]"
```

## Task 4: Add Database Index And Migration Updates

**Files:**
- Modify: `passport-platform/src/passport_platform/db.py`
- Modify: `passport-platform/migrations/`

- [ ] **Step 1: Update the reference migration SQL with the new uploads index**

```sql
CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at_id_desc
    ON uploads (user_id, created_at DESC, id DESC);
```

- [ ] **Step 2: Add the same index to runtime initialization**

```python
CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at_id_desc
    ON uploads (user_id, created_at DESC, id DESC);
```

- [ ] **Step 3: Add a startup upgrade guard only if the current migration pattern requires it**

```python
@staticmethod
def _upgrade_schema(conn: sqlite3.Connection) -> None:
    ...
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at_id_desc ON uploads (user_id, created_at DESC, id DESC)"
    )
```

- [ ] **Step 4: Run platform tests that exercise record listing**

Run: `uv run pytest passport-platform/tests/test_records_service.py -q`

Expected: PASS with no schema regressions.

- [ ] **Step 5: Commit the schema/index change**

```bash
git add passport-platform/src/passport_platform/db.py passport-platform/migrations
git commit -m "feat: add slim records list index [codex]"
```

## Task 5: Switch The Background Worker To Slim Endpoints

**Files:**
- Modify: `passport-masar-extension/background.js`
- Modify: `passport-masar-extension/tests/background.test.js`

- [ ] **Step 1: Write failing background tests for page fetch, counts fetch, and id discovery**

```javascript
test("FETCH_RECORD_PAGE requests sectioned paginated records", async () => {
  const response = await handleMessage({
    type: "FETCH_RECORD_PAGE",
    section: "pending",
    limit: 50,
    offset: 0,
  });
  expect(response.ok).toBe(true);
});

test("FETCH_RECORD_COUNTS returns server counts payload", async () => {
  const response = await handleMessage({ type: "FETCH_RECORD_COUNTS" });
  expect(response.data).toEqual({ pending: 1, submitted: 0, failed: 0 });
});

test("FETCH_SUBMIT_ELIGIBLE_IDS returns id page only", async () => {
  const response = await handleMessage({
    type: "FETCH_SUBMIT_ELIGIBLE_IDS",
    section: "pending",
    limit: 100,
    offset: 0,
  });
  expect(response.data.items[0]).toEqual({
    upload_id: 10,
    upload_status: "processed",
    review_status: "auto",
    masar_status: null,
  });
});
```

- [ ] **Step 2: Run the background test file and verify failure**

Run: `npm test -- passport-masar-extension/tests/background.test.js`

Expected: FAIL because those message types and fetch helpers do not exist.

- [ ] **Step 3: Replace `fetchAllRecords` with focused fetch helpers**

```javascript
async function fetchRecordPage(section, limit, offset) {
  const response = await apiFetch(`/records?section=${encodeURIComponent(section)}&limit=${limit}&offset=${offset}`);
  if (!response.ok) {
    if (response.status === 401) {
      await localSet({ session_expired: true });
      await updateBadgeState({ failedCount: 0 });
      return { ok: false, status: 401, failureKind: "backend-auth" };
    }
    return { ok: false, status: response.status, failureKind: null };
  }
  await localSet({ session_expired: false });
  return { ok: true, data: await response.json() };
}

async function fetchRecordCounts() {
  const response = await apiFetch("/records/counts");
  if (!response.ok) {
    return { ok: false, status: response.status, failureKind: response.status === 401 ? "backend-auth" : null };
  }
  return { ok: true, data: await response.json() };
}

async function fetchSubmitEligibleIds(limit, offset) {
  const response = await apiFetch(`/records/ids?section=pending&limit=${limit}&offset=${offset}`);
  if (!response.ok) {
    return { ok: false, status: response.status, failureKind: response.status === 401 ? "backend-auth" : null };
  }
  return { ok: true, data: await response.json() };
}
```

Error propagation contract stays aligned with the existing background worker: `401` maps to `backend-auth`, non-401 failures stay generic, and popup-level retry/login handling remains in the popup layer. Add at least one background test covering a `401` response from `FETCH_RECORD_PAGE`.

- [ ] **Step 4: Add new message handlers and keep detail/image fetches intact**

```javascript
if (msg.type === "FETCH_RECORD_PAGE") {
  return fetchRecordPage(msg.section, msg.limit, msg.offset);
}
if (msg.type === "FETCH_RECORD_COUNTS") {
  return fetchRecordCounts();
}
if (msg.type === "FETCH_SUBMIT_ELIGIBLE_IDS") {
  return fetchSubmitEligibleIds(msg.limit, msg.offset);
}
```

- [ ] **Step 5: Re-run the background tests**

Run: `npm test -- passport-masar-extension/tests/background.test.js`

Expected: PASS for new background API helpers.

- [ ] **Step 6: Commit the background API consumption update**

```bash
git add passport-masar-extension/background.js passport-masar-extension/tests/background.test.js
git commit -m "feat: add slim records background fetchers [codex]"
```

## Task 6: Migrate The Popup Data Model To Per-Tab Cache

**Files:**
- Modify: `passport-masar-extension/popup.js`
- Modify: `passport-masar-extension/queue-filter.js`
- Modify: `passport-masar-extension/tests/popup.test.js`
- Modify: `passport-masar-extension/tests/queue-filter.test.js`
- Modify: `passport-masar-extension/tests/popup-failure.test.js`

- [ ] **Step 1: Write failing popup tests for boot behavior and tab-local fetching**

```javascript
test("workspace boot fetches counts and active tab page only", async () => {
  await bootstrapPopup();
  expect(sendMessage).toHaveBeenCalledWith(
    expect.objectContaining({ type: "FETCH_RECORD_COUNTS" }),
    expect.anything(),
  );
  expect(sendMessage).toHaveBeenCalledWith(
    expect.objectContaining({ type: "FETCH_RECORD_PAGE", section: "pending", limit: 50, offset: 0 }),
    expect.anything(),
  );
});

test("switching tabs fetches page one for that tab only once", async () => {
  await bootstrapPopup();
  await clickSubmittedTab();
  await clickPendingTab();
  expect(fetchRecordPageCalls("submitted")).toHaveLength(1);
});
```

- [ ] **Step 2: Run popup and queue-filter tests to verify failure**

Run: `npm test -- passport-masar-extension/tests/popup.test.js passport-masar-extension/tests/queue-filter.test.js passport-masar-extension/tests/popup-failure.test.js`

Expected: FAIL because the popup still uses `lastFetchedRecords` and workspace-wide fetch-all.

- [ ] **Step 3: Replace global records state with tab caches and counts state**

```javascript
state.tabCache = {
  pending: { items: [], total: 0, offset: 0, hasMore: false, loaded: false, loading: false, error: null, lastLoadedAt: 0 },
  inProgress: { items: [], total: 0, offset: 0, hasMore: false, loaded: true, loading: false, error: null, lastLoadedAt: 0 },
  submitted: { items: [], total: 0, offset: 0, hasMore: false, loaded: false, loading: false, error: null, lastLoadedAt: 0 },
  failed: { items: [], total: 0, offset: 0, hasMore: false, loaded: false, loading: false, error: null, lastLoadedAt: 0 },
};
state.countsState = { server: null, derived: null, stale: false, loading: false };
```

`inProgress.loaded = true` is intentional. That tab is local-session-derived and should never trigger a server fetch. Document this in code comments and in `docs/EXTENSION.md` so it is not mistaken for a stale-cache bug.

- [ ] **Step 4: Add `loadCounts`, `loadTabPage`, and `renderWorkspaceFromCache`**

```javascript
async function loadTabPage(tab, { append = false, silent = false } = {}) {
  const cache = state.tabCache[tab];
  const offset = append ? cache.offset : 0;
  const response = await sendMsg({ type: "FETCH_RECORD_PAGE", section: mapTabToSection(tab), limit: 50, offset }, { timeoutMs: 10000 });
  ...
}
```

- [ ] **Step 5: Replace queue filtering with server-section merge helpers**

```javascript
function filterServerSections(caches) {
  return {
    pending: caches.pending.items,
    submitted: caches.submitted.items,
    failed: caches.failed.items,
  };
}

function mergeOptimisticSections({ serverSections, batchState }) {
  ...
}
```

- [ ] **Step 6: Re-run popup, queue-filter, and failure tests**

Run: `npm test -- passport-masar-extension/tests/popup.test.js passport-masar-extension/tests/queue-filter.test.js passport-masar-extension/tests/popup-failure.test.js`

Expected: PASS for tab-local fetching, cache reuse, and no full-screen timeout regression after initial render.

- [ ] **Step 7: Commit the popup data-model rewrite**

```bash
git add passport-masar-extension/popup.js passport-masar-extension/queue-filter.js passport-masar-extension/tests/popup.test.js passport-masar-extension/tests/queue-filter.test.js passport-masar-extension/tests/popup-failure.test.js
git commit -m "feat: add tabbed popup records cache [codex]"
```

## Task 7: Introduce Rich Optimistic Batch State And Resume Semantics

**Files:**
- Modify: `passport-masar-extension/background.js`
- Modify: `passport-masar-extension/popup.js`
- Modify: `passport-masar-extension/tests/background.test.js`
- Modify: `passport-masar-extension/tests/popup.test.js`

- [ ] **Step 1: Write failing tests for optimistic batch seeding, resume, and blocked state**

```javascript
test("submit all seeds submission_batch after first ids page", async () => {
  await clickSubmitAll();
  expect(sessionSet).toHaveBeenCalledWith(
    expect.objectContaining({
      submission_batch: expect.objectContaining({
        active_id: 10,
        queued_ids: [11, 12],
      }),
    }),
  );
});

test("popup reopen restores banner and optimistic counts from session batch", async () => {
  mockSessionBatch();
  await bootstrapPopup();
  expect(screen.getByText("جارٍ رفع الجوازات")).toBeTruthy();
});
```

- [ ] **Step 2: Run the targeted extension tests and verify failure**

Run: `npm test -- passport-masar-extension/tests/background.test.js passport-masar-extension/tests/popup.test.js`

Expected: FAIL because `submission_batch` is still an array and the popup has no banner/count reconstruction logic.

- [ ] **Step 3: Change `submission_batch` to the richer object shape**

```javascript
const batchState = {
  batch_id: crypto.randomUUID(),
  discovered_ids: [10, 11, 12],
  queued_ids: [11, 12],
  active_id: 10,
  submitted_ids: [],
  failed_ids: [],
  blocked_ids: [],
  blocked_reason: null,
  exhausted_source: false,
  next_offset: 100,
  source_total: 240,
  started_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};
```

- [ ] **Step 4: Seed the batch from `/records/ids` and continue discovery lazily**

```javascript
async function startSubmitBatch() {
  const firstPage = await fetchSubmitEligibleIds(100, 0);
  await sessionSet({ submission_batch: buildInitialBatchState(firstPage.data) });
  serialiseSubmit(() => resumeSubmissionBatch());
}
```

- [ ] **Step 5: Add the lazy discovery loop that advances `next_offset` while drain is running**

```javascript
async function continueBatchDiscovery(batch) {
  let nextOffset = batch.next_offset;
  while (!batch.exhausted_source && nextOffset < batch.source_total) {
    const response = await fetchSubmitEligibleIds(100, nextOffset);
    if (!response.ok) {
      return {
        ...batch,
        exhausted_source: false,
        discovery_error: true,
      };
    }
    batch = appendDiscoveredIds(batch, response.data.items, response.data.total, nextOffset + response.data.items.length);
    await sessionSet({ submission_batch: batch });
    nextOffset = batch.next_offset;
    if (batch.active_id == null && batch.queued_ids.length === 0) {
      break;
    }
  }
  return { ...batch, exhausted_source: nextOffset >= batch.source_total };
}
```

- [ ] **Step 6: Preserve blocked state instead of clearing the batch on auth/contract failures**

```javascript
if (shouldBlockBatch(result)) {
  await sessionSet({
    submission_batch: {
      ...batch,
      blocked_reason: result.failureKind,
      updated_at: new Date().toISOString(),
    },
  });
  return result;
}
```

- [ ] **Step 7: Re-run the background and popup tests**

Run: `npm test -- passport-masar-extension/tests/background.test.js passport-masar-extension/tests/popup.test.js`

Expected: PASS for optimistic seed, resume, and blocked-state preservation.

- [ ] **Step 8: Commit the optimistic queue state migration**

```bash
git add passport-masar-extension/background.js passport-masar-extension/popup.js passport-masar-extension/tests/background.test.js passport-masar-extension/tests/popup.test.js
git commit -m "feat: add optimistic batch resume state [codex]"
```

## Task 8: Redesign The Passport Cards And Banner

**Files:**
- Modify: `passport-masar-extension/popup.js`
- Modify: `passport-masar-extension/strings.js`
- Modify: popup HTML/CSS files in `passport-masar-extension/` that own card layout and workspace styles
- Modify: `passport-masar-extension/tests/popup.test.js`

- [ ] **Step 1: Write failing UI tests for the progress banner and simplified card content**

```javascript
test("active batch shows progress banner with summary and refresh action", async () => {
  mockSessionBatch();
  await bootstrapPopup();
  expect(screen.getByText("جارٍ رفع الجوازات")).toBeTruthy();
  expect(screen.getByText(/تم رفع/)).toBeTruthy();
  expect(screen.getByText("تحديث")).toBeTruthy();
});

test("row renders name passport state and one note only", async () => {
  await bootstrapPopup();
  const card = getFirstPendingCard();
  expect(card.textContent).toContain("12345678");
  expect(card.querySelectorAll(".record-note").length).toBe(1);
});
```

- [ ] **Step 2: Run the popup test file and confirm the UI assertions fail**

Run: `npm test -- passport-masar-extension/tests/popup.test.js`

Expected: FAIL because the current UI has no progress banner and richer card composition.

- [ ] **Step 3: Add Arabic strings in `strings.js`**

```javascript
PROGRESS_BANNER_TITLE: "جارٍ رفع الجوازات",
PROGRESS_BANNER_SUMMARY: (done, total) => `تم رفع ${done} من ${total}`,
PROGRESS_BANNER_DETAIL: (active, queued) => `جواز واحد جارٍ رفعه و${queued} في الانتظار`,
LIST_REFRESH_FAILED: "تعذر تحديث القائمة",
BATCH_START_FAILED: "تعذر بدء الرفع",
BATCH_DISCOVERY_FAILED: "تعذر تحميل بقية الجوازات",
ACTION_RESUME: "استئناف",
```

- [ ] **Step 4: Redesign the rendered card structure around stable operational rows**

```javascript
function renderRecordCard(doc, record) {
  const article = doc.createElement("article");
  article.className = "record-card";
  article.append(
    buildCardHeader(doc, record),
    buildCardNote(doc, record),
    buildCardActions(doc, record),
  );
  return article;
}
```

- [ ] **Step 5: Update styles for the new warm utilitarian workspace direction**

```css
.workspace-root {
  --workspace-bg: #f4eedf;
  --workspace-panel: rgba(255, 251, 242, 0.92);
  --workspace-ink: #233127;
  --workspace-accent: #667b51;
  --workspace-danger: #9f4a34;
}
```

Apply these variables on the popup root container, not global `:root`, to avoid accidental bleed across extension surfaces.

- [ ] **Step 6: Re-run the popup tests**

Run: `npm test -- passport-masar-extension/tests/popup.test.js`

Expected: PASS for banner presence, simplified card content, and stable action rendering.

- [ ] **Step 7: Commit the popup redesign**

```bash
git add passport-masar-extension/popup.js passport-masar-extension/strings.js passport-masar-extension/tests/popup.test.js passport-masar-extension
git commit -m "feat: redesign popup passport cards [codex]"
```

## Task 9: Update Docs And Run Full Verification

**Files:**
- Modify: `docs/EXTENSION.md`
- Modify: `passport-api/README.md`
- Modify: `passport-platform/README.md`

- [ ] **Step 1: Update extension docs for the new popup state model**

```markdown
- `GET /records` is now a slim paginated workspace feed.
- `GET /records/counts` provides server badge counts.
- `GET /records/ids` provides submit-eligible discovery for `رفع الكل`.
- `chrome.storage.session.submission_batch` is the optimistic queue source of truth.
```

- [ ] **Step 2: Update API and platform READMEs for the heavy-detail boundary**

```markdown
- `GET /records/{upload_id}` remains the heavy detail endpoint.
- List responses omit OCR blobs, image URIs, and heavy extraction fields.
```

- [ ] **Step 3: Run Python quality gates from the worktree root**

Run: `uv run ruff check passport-api passport-platform`

Expected: PASS

Run: `uv run ruff format passport-api passport-platform`

Expected: files formatted with no remaining diff from formatter.

Run: `uv run ty check passport-api passport-platform`

Expected: PASS

Run: `uv run pytest passport-api/tests/test_api.py passport-platform/tests/test_records_service.py -q`

Expected: PASS

- [ ] **Step 4: Run extension tests**

Run: `npm test -- passport-masar-extension/tests/background.test.js passport-masar-extension/tests/popup.test.js passport-masar-extension/tests/queue-filter.test.js passport-masar-extension/tests/popup-failure.test.js`

Expected: PASS

- [ ] **Step 5: Add one automated boot test for the 200-plus-record scenario**

```javascript
test("workspace boot with total over 200 still fetches only pending page one", async () => {
  mockRecordPage({ items: buildRecords(50), total: 240, has_more: true, limit: 50, offset: 0 });
  await bootstrapPopup();
  expect(fetchRecordPageCalls("pending")).toHaveLength(1);
  expect(fetchRecordPageCalls("submitted")).toHaveLength(0);
  expect(fetchRecordPageCalls("failed")).toHaveLength(0);
});
```

- [ ] **Step 6: Run package-boundary validation if imports changed**

Run: `uv run lint-imports`

Expected: PASS

- [ ] **Step 7: Perform manual checks in the extension**

Run these manual checks:
- open popup with more than 200 records and confirm only pending page 1 loads
- switch tabs and confirm no full-screen wipe
- trigger `رفع الكل` and confirm banner appears after first ids page
- close and reopen popup mid-batch and confirm counts/banner restore
- verify failed records show Arabic-only failure notes

- [ ] **Step 8: Commit docs and verification results**

```bash
git add docs/EXTENSION.md passport-api/README.md passport-platform/README.md
git commit -m "docs: document slim records popup flow [codex]"
```

## Self-Review Checklist

- Spec coverage:
  - slim `/records` contract: Tasks 1, 2, 3
  - heavy detail endpoint retained: Task 3
  - counts and ids endpoints: Tasks 1, 2, 3, 5
  - per-tab popup caching: Task 6
  - optimistic batch and resume behavior: Task 7
  - passport card redesign: Task 8
  - docs and verification: Task 9

- Placeholder scan:
  - No `TODO`, `TBD`, or deferred implementation markers remain.

- Type consistency:
  - `RecordListItemResponse`, `UserRecordListItem`, `UserRecordListResult`, `RecordCountsResponse`, and `submission_batch` object naming are consistent across tasks.
