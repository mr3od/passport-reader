# Extension UI Redesign — Design Spec

**Date:** 2026-03-31
**Scope:** `passport-masar-extension`, `passport-platform`, `passport-api`
**Reference docs:** `docs/final-design-proposal.html` (preserved final design mock), `docs/brainstoorming-refined.md` (supporting design history only), and the current extension popup files under `passport-masar-extension/`

---

## Overview

Full rebuild of the extension popup UI from a single pending-only queue into a tabbed four-section workspace. Tabs: Pending (ready to submit) / In Progress (admitted into active batch) / Submitted / Failed. Adds Submit All with snapshot-then-drain batch model, click-to-redirect for submitted records, contract selection, context-change notifications, badge priority system, and removes the pre-submit review gate.

---

## Design Decisions

| Topic | Decision |
|---|---|
| Main workspace layout | Tabs (Pending / In Progress / Submitted / Failed) |
| Summary strip | Office name + contract pill + Pending count + Failed count (red if >0) |
| Submit All | Snapshots all Pending records → moves to In Progress → drains sequentially; single count confirmation dialog |
| `needs_review` gate | Removed — submit directly, amber badge persists after submission |
| Context change UI | Chrome notification + inline banner; the earlier full-screen context-change concept was dropped |
| Relink | Preserves selected group |
| Contract select | NEW — fetches contracts via `GetContractList`; dropdown when multiple active (`contractStatus.id === 0`); auto-selects when one; selectable (writes `masar_contract_id` to storage on change) |
| Click-to-redirect | Uses `masar_detail_id` from step 7; "تفاصيل غير متوفرة" if null |
| Mutamer detail URL | `https://masar.nusuk.sa/umrah/mutamer/mutamer-details/{encodeURIComponent(masar_detail_id)}` |
| `review_status` mapping | Computed client-side: `record.review_status === "needs_review"` (API field stays string) |
| Field name | `masar_detail_id` (new) alongside existing `masar_mutamer_id` |

---

## Status / Badge Matrix

Tab placement is determined by submission lifecycle state. Badge styling is determined by `review_status`.

### Pending tab (ready to submit, not yet in batch)

`upload_status=processed`, `masar_status=null`, `upload_id` NOT in `submission_batch`.

| `review_status` | Badge | Actions |
|---|---|---|
| `auto` or `reviewed` | Blue "جاهز" | Submit, Skip |
| `needs_review` | Amber "يحتاج مراجعة" | Submit, Skip (no gate, no dialog) |

### In Progress tab (admitted into active batch)

`upload_status=processed`, `masar_status=null`, `upload_id` IS in `submission_batch`.

`submission_batch` is a `chrome.storage.session` key (array of upload_ids). `chrome.storage.session` persists across service worker restarts within the same browser session but is cleared on browser close. This prevents permanent stranding across browser restarts. However, if the service worker is killed mid-batch and restarts within the same session, stale IDs can remain — background.js must reconcile on startup by clearing `submission_batch` and `active_submit_id` if no submission is actively running.

`active_submit_id` is a companion `chrome.storage.session` key (single upload_id or null) set by background.js to the record currently running the 6-step flow. This lets the popup distinguish the two In Progress row states without ambiguity:

| State | Condition | Badge | Actions |
|---|---|---|---|
| Currently submitting | `upload_id === active_submit_id` | Gray "جاري الرفع" + spinner | None |
| Queued in batch | in `submission_batch` AND `upload_id !== active_submit_id` | Gray "في الانتظار" + spinner | None |

### Submitted tab

| Record state | Badge | Action |
|---|---|---|
| `masar_status=submitted`, `review_status≠needs_review` | Green "تم الرفع" | Click card → open Nusuk detail |
| `masar_status=submitted`, `review_status=needs_review` | Amber "تم الرفع - يحتاج مراجعة" | Click card → open Nusuk detail |
| Either above, `masar_detail_id=null` | Same badge | "تفاصيل غير متوفرة" (no click) |

### Failed tab

| Record state | Badge | Actions |
|---|---|---|
| `masar_status=failed` OR `upload_status=failed` | Red "فشل" | Retry |

### Extension badge priority

| Priority | Condition | Badge | Color |
|---|---|---|---|
| 1 (highest) | Session expired | `!` | Red `#D32F2F` |
| 2 | Context change pending | `!` | Orange `#F57C00` |
| 3 | Failed count > 0 | `{n}` | Red `#D32F2F` |
| 4 | Clear | `` | — |

---

## Implemented Screen Inventory

The current popup implementation is organized around concrete screen IDs and one main workspace rather than the older numbered-scene proposal set.

| Screen / Area | Status | Notes |
|---|---|---|
| `screen-setup` | Kept | Token-first linking state |
| `screen-activate` | Kept | Waits for Masar context capture |
| `screen-session-expired` | Kept | Dedicated Masar relogin state |
| `screen-group-select` | Kept | Minimal select-and-confirm flow |
| `screen-main` | Canonical workspace | Summary strip, contract selector, toolbar, tabs, and context banner |
| `screen-settings` | Kept | Secondary configuration surface |
| `screen-loading` | Kept | Transitional loading state |
| `screen-error` | Kept | Generic fallback state |
| `context-change-banner` | Kept | Inline handling for entity/contract drift |
| `contract-dropdown-container` | Kept | Appears only when multiple active contracts exist |

---

## Backend Changes

### passport-platform

**`services/records.py`**
- `assert_submission_allowed()`: add `"needs_review"` to the allowed set.
  ```python
  # Before
  if record.review_status in {"auto", "reviewed"}:
  # After
  if record.review_status in {"auto", "reviewed", "needs_review"}:
  ```

**`db.py`**
- Add column to `masar_submissions` table:
  ```sql
  masar_detail_id TEXT
  ```
- Update `INDEX_SQL` and migration baseline in `migrations/*.sql`.

**`models/upload.py`**
- `MasarSubmission`: add `masar_detail_id: str | None = None`
- Do NOT touch `ProcessingResult` — it stores OCR data only.

**`repositories/records.py`**
- `_LATEST_MASAR_SUBMISSION_JOIN`: add `ms1.masar_detail_id AS masar_detail_id` to the inner SELECT
- `_USER_RECORD_COLUMNS`: add `ms.masar_detail_id AS masar_detail_id`
- `insert_masar_submission()`: add `masar_detail_id` parameter; include in `INSERT` values
- `_row_to_user_record()`: wire `masar_detail_id=row["masar_detail_id"]`

**`services/records.py`**
- `update_masar_status()`: accept and pass through optional `masar_detail_id: str | None = None`

**`schemas/results.py`**
- `UserRecord`: add `masar_detail_id: str | None = None`

### passport-api

**`schemas.py`**
- `MasarStatusUpdate`: add `masar_detail_id: str | None = None`
- `RecordResponse`: add `masar_detail_id: str | None = None`

**`routes/records.py`**
- `PATCH /records/{upload_id}/masar-status`: pass `masar_detail_id` through to service.
- `_record_to_response()`: add `masar_detail_id=record.masar_detail_id` to `RecordResponse` constructor.

---

## Extension Changes

### New modules

**`strings.js`**
Frozen object of all Arabic UI strings. Keys include:
`STATUS_READY`, `STATUS_NEEDS_REVIEW`, `STATUS_IN_PROGRESS`, `STATUS_QUEUED_IN_BATCH`, `STATUS_SUBMITTED`, `STATUS_SUBMITTED_NEEDS_REVIEW`, `STATUS_FAILED`, `SECTION_PENDING`, `SECTION_IN_PROGRESS`, `SECTION_SUBMITTED`, `SECTION_FAILED`, `ACTION_SUBMIT`, `ACTION_SUBMIT_ALL`, `ACTION_RETRY`, `VIEW_DETAILS`, `DETAILS_UNAVAILABLE`, `CTX_CHANGE_PROMPT`, `CTX_CHANGE_YES`, `CTX_CHANGE_LATER`, `CTX_CHANGED_ENTITY`, `CTX_CHANGED_CONTRACT`, `NOTIF_BATCH_COMPLETE`, `NOTIF_SESSION_EXPIRED`, `CONTRACT_EXPIRED`, `HELP_LINK_LABEL`.

No `SECTION_QUEUE` — the old "Queue" tab is now "Pending" (`SECTION_PENDING`). No `STATUS_PROCESSING` (OCR status not shown in extension).

**`status.js`**
```javascript
getStatusLabel({ upload_status, masar_status, review_status, inProgress }): string
getStatusColor({ upload_status, masar_status, review_status, inProgress }): string
```
Priority: failed → submitted+needs_review → submitted → in_progress → pending+needs_review → ready → default.
`review_status === "needs_review"` is the boolean test. `inProgress` is a boolean passed from the caller (derived from `submission_batch`), not an API field.

**`queue-filter.js`**
```javascript
filterQueueSections(records, inProgressIds = new Set()): { pending, inProgress, submitted, failed }
```
- `failed`: `upload_status=failed` OR `masar_status=failed`
- `submitted`: `masar_status=submitted`
- `inProgress`: `upload_status=processed` AND `masar_status=null` AND `inProgressIds.has(upload_id)`
- `pending`: `upload_status=processed` AND `masar_status=null` AND NOT in `inProgressIds`
- Every record in exactly one section.
- `inProgressIds` is a `Set<number>` populated from `submission_batch` in `chrome.storage.session`. Defaults to empty set (all submittable records go to `pending`).
- `active_submit_id` is passed separately to `status.js` for In Progress row badge differentiation — it is not used inside `filterQueueSections`.

**`badge.js`**
```javascript
computeBadgeState({ sessionExpired, contextChangePending, failedCount }): { text, color, priority }
applyBadge({ text, color }): void
```

**`notifications.js`**
```javascript
notify(type, message, title?): void
NOTIFICATION_TYPES: { CONTEXT_CHANGE, SESSION_EXPIRED, BATCH_COMPLETE }
```
30-second dedup per type. No `NEEDS_REVIEW` type — `needs_review` is an internal flag, not a Nusuk event.

**`context-change.js`**
```javascript
detectContextChange({ entity_id, contract_id, auth_token }): Promise<{ reason } | null>
applyContextChange(): Promise<void>
hasContextChangePending(): Promise<boolean>
clearPendingContextChange(): Promise<void>
getContextChangeReason(): Promise<string | null>
createDebouncedContextChecker(callback, delayMs): function
SUBMISSION_STATES: { IDLE, SUBMITTING_CURRENT, QUEUED_MORE }
getSubmissionState(): Promise<string>
setSubmissionState(state): Promise<void>
shouldStopSubmission(): Promise<boolean>  // false only when SUBMITTING_CURRENT
```
Reasons: `entity_changed`, `contract_changed`.

**`contract-select.js`**
```javascript
fetchContracts(): Promise<contract[]>
resolveContractSelection(contracts): { selectedContract, showDropdown }
```

`fetchContracts()` calls:
```
POST https://masar.nusuk.sa/umrah/contracts_apis/api/ExternalAgent/GetContractList
body: {"umrahCompanyName":null,"contractStartDate":null,"contractEndDate":null}
```
Uses `masarFetch()`. Response at `response.data.contracts`.

Active contract filter: `contractStatus?.id === 0`. Do NOT use `active === true`.

`resolveContractSelection(contracts)` filters to active contracts then:
- 0 active → `{null, false}`
- 1 active → `{that, false}`
- 2+ active → `{null, true}`

**RESOLVED — contract switching:** Selectable dropdown. When multiple active contracts exist, the user can pick one from the dropdown. Selecting a different contract writes `masar_contract_id` to `chrome.storage.local`, which changes the `contractid` header on subsequent Masar API calls. If Masar rejects the mismatched contract, the submission fails with a recoverable error (same as any other step failure). No backward-compatibility handling needed — dev phase.

### Modified files

**`manifest.json`**
- Add `"notifications"` to `permissions`.

**`popup.html`**
New required elements:
- `div#context-change-banner[hidden]` with `button#ctx-change-confirm`, `button#ctx-change-defer`
- `div#home-summary` with `span#pending-count`, `span#failed-count`
- `div#contract-dropdown-container[hidden]` with `select#contract-select`
- Tab bar: 4 tab buttons with `data-tab` attributes and `span.tab-count` per tab
- `div#pending-section` with `button#submit-all-btn`
- `div#in-progress-section`
- `div#submitted-section`
- `div#failed-section`
- `a#help-support-link`
- No `needs-review-section` — `needs_review` records are shown inside the Pending tab with amber badge.

**`popup.css`**
- Tab bar styles (`.tabs`, `.tab`, `.tab.active`, `.tab-count`)
- Section block styles (`.section-block`, `.section-header`, `.section-title`)
- Passport thumbnail (`.passport-thumb` — 52×64px)
- Detail link (`.detail-link`, `.detail-link.muted`)
- Rich record layout (`.record.rich` — thumbnail + content grid)
- Context change banner styles

**`popup.js`**
Key behavioral changes:
- **Remove** confirm + `MARK_REVIEWED` submit path. All pending records submit directly.
- **Submit All flow:**
  1. Show confirmation dialog: "هل تريد رفع {n} جواز؟"
  2. On confirm: snapshot current Pending record IDs → send `SUBMIT_BATCH` message to background with the snapshot array
  3. Background writes snapshot to `submission_batch` in storage, then drains sequentially
  4. Popup re-renders on each storage change: records move from Pending → In Progress → Submitted/Failed as batch drains
- **Individual submit**: sends `SUBMIT_RECORD` for a single record; background adds it to `submission_batch`, processes it, removes it when done
- **Submitted card click**: if `record.masar_detail_id` → `chrome.tabs.create({ url })`. Else no-op.
- **Context change banner**: reads `pending_context_change` from storage on init; shows/hides banner; Confirm → `sendMessage(APPLY_CONTEXT_CHANGE)`; Defer → hide locally, keep pending in storage.
- **Contract dropdown**: shown when `resolveContractSelection().showDropdown`. Selectable — user can pick a different active contract. On change: write new `masar_contract_id` to `chrome.storage.local`. Pre-selects the contract matching the current `masar_contract_id` from storage.
- **Home summary**: sets `#pending-count` and `#failed-count` from `filterQueueSections()` result.
- **Contract-expired lock**: when `masar_contract_state === "expired"` (read from storage on init), disable `#submit-all-btn` and all individual Submit buttons in the Pending tab. No special behavior for any other contract state — only `"expired"` disables submission.

Exported functions (for testing):
`renderPendingCard(document, record)`, `renderHomeSummary(document, { pendingCount, failedCount })`, `handleCardClick({ clickUrl })`, `initContextChangeBanner(document)`.

**`background.js`**
Key behavioral changes:
- Import `context-change.js`, `badge.js`, `notifications.js`.
- Debounced context checker at module level (1500ms).
- `webRequest` listener: first run → write directly; subsequent → debounced check.
- `handleStableContextChange()`: calls `detectContextChange()` → if change: buffer to storage, update badge, `notify(CONTEXT_CHANGE, ...)`.
- `APPLY_CONTEXT_CHANGE` message: calls `applyContextChange()` + badge update.
- Export `shouldSubmitRecord(record)`: returns `true` if `upload_status=processed` AND (`masar_status` null/undefined OR `masar_status=failed`). `review_status` has NO effect.
- **Remove** `needs_review` hard reject in `SUBMIT_RECORD` handler.
- **Session storage keys** — use `chrome.storage.session` (not `local`) for all batch state. Session storage survives service worker restarts within the same browser session but is cleared on browser close, preventing permanent stranding across restarts. A mid-batch worker restart within the same session can still leave stale keys — background.js must clear `submission_batch` and `active_submit_id` on startup (service worker `install`/`activate` or first message) if no submission is actively running:
  - `submission_batch`: `number[]` — upload_ids admitted into the active batch
  - `active_submit_id`: `number | null` — the single record currently running the 6-step flow
  - `SUBMIT_BATCH` message: receives `uploadIds[]` snapshot → writes to `submission_batch`, sets `active_submit_id = null` → drains sequentially: before each record set `active_submit_id = uploadId`, after resolve remove from `submission_batch` and clear `active_submit_id` → when batch empty `notify(BATCH_COMPLETE, ...)`
  - `SUBMIT_RECORD` message (single): appends `upload_id` to `submission_batch`, sets `active_submit_id = uploadId` → processes → removes from `submission_batch`, clears `active_submit_id`
  - Popup reads both keys and passes them to `filterQueueSections()` and `status.js`
- Submission loop: `setSubmissionState(SUBMITTING_CURRENT)` per record, `shouldStopSubmission()` between records, `setSubmissionState(IDLE)` after batch, `notify(BATCH_COMPLETE, ...)`.
- **Step 7 (new)** after successful 6-step submission — fetch the Nusuk detail token:
  ```javascript
  // passportNumber = core.PassportNumber || scan.passportNumber (same as step2Body)
  const listRes = await masarFetch(
    'https://masar.nusuk.sa/umrah/groups_apis/api/Mutamer/GetMutamerList',
    {
      method: 'POST',
      body: JSON.stringify({
        limit: 10, offset: 0, noCount: true,
        sortColumn: null, sortCriteria: [],
        filterList: [{ propertyName: 'passportNumber', operation: 'match', propertyValue: passportNumber }]
      })
    }
  );
  const masar_detail_id = listRes.ok
    ? ((await listRes.json())?.response?.data?.content?.[0]?.id ?? null)
    : null;
  ```
  `masarFetch()` returns a `Response` — must call `await listRes.json()` before reading data. Response envelope: `response.data.content[0].id` (verified from HAR).
  Include `masar_detail_id` in `PATCH /records/{id}/masar-status` payload.
- Keep `MARK_REVIEWED` message handler (for future/manual use). Extension no longer calls it during submission.
- `FETCH_ALL_RECORDS` new message: calls `GET /records` (limit 200), returns all records for client-side filtering by `filterQueueSections()`. Popup reads `submission_batch` and `active_submit_id` from `chrome.storage.session` and passes them to `filterQueueSections()` and `status.js` respectively.

**`strings.js` cleanup (review-gate removal)**

The new `strings.js` module (listed above under New modules) does not carry over these legacy keys from the current `strings.js`:
- `REVIEW_CONFIRM` — was the `window.confirm` dialog text ("هذه البيانات تحتاج مراجعة قبل الرفع. هل تؤكد المتابعة؟"); removed with the confirm+MARK_REVIEWED path
- `REVIEW_UPDATE_FAILED` — was the error shown when `MARK_REVIEWED` failed; removed with that flow
- `REVIEW_REQUIRED` — old value said "تحتاج مراجعة قبل الرفع" ("before upload"); the replacement key `STATUS_NEEDS_REVIEW` must not include "before upload" phrasing. Suggested value: `"يحتاج مراجعة"` (badge label only)

---

## Submission Gate Change — Test Impact

The following tests assume `review_status=needs_review` blocks submission and must be updated:

| Layer | Test location | Change needed |
|---|---|---|
| Platform | `passport-platform/tests/` — `assert_submission_allowed` tests | Expect success (not 409) for `needs_review` |
| API | `passport-api/tests/` — `PATCH /records/{id}/masar-status` tests | Expect 200 for `needs_review` records without prior MARK_REVIEWED |
| Extension | `popup.js` tests | Remove confirm+MARK_REVIEWED path from submit flow |
| Extension | `background.js` tests | `shouldSubmitRecord` returns `true` for `needs_review` |
| Extension | `queue-filter.js` tests | `pending` = processed + masar_status null + not in inProgressIds; `inProgress` = processed + masar_status null + in inProgressIds |

---

## Dependency Graph — Implementation Order

```
strings.js (1)
  ├── status.js (2)
  ├── context-change.js (2)
  └── popup.html (2)

status.js (2) ──────────────────┐
queue-filter.js (2) ────────────┤──→ popup.js cards (3)
badge.js (2) ──────────────────→ background.js (3)
notifications.js (2) ──────────→ background.js (3)
context-change.js (2) ─────────→ popup.js banner (3), background.js (3)
contract-select.js (2) ────────→ popup.js contract (3)

Backend changes (parallel, any order):
  platform db + model + repo + service
  api schemas + route

manifest.json (standalone)
Telegram strings (standalone)
Test updates (after each layer)
```

**Execution order:**
1. Backend: platform schema + service gate change
2. Backend: API schema
3. `strings.js`
4. `status.js`, `queue-filter.js`, `badge.js`, `notifications.js`, `context-change.js`, `contract-select.js` (parallel)
5. `popup.html` + `popup.css`
6. `popup.js` (cards, submit-all, context banner, contract select, click-to-redirect)
7. `background.js` (step 7, submission state machine, context change integration)
8. `manifest.json`
9. Test updates across all layers

---

## What Is NOT in Scope

- Telegram message text rewrite (separate task, standalone)
- `MARK_REVIEWED` endpoint removal (kept for future manual use)
- Batch review from the popup
- Pagination in the submitted/failed tabs (limit 200 is sufficient)
- Any Masar group assignment on submission (records remain group-unlinked in our backend)
