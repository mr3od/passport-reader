# Extension Archive Lane And Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement archive/unarchive for agency uploads with `uploads.archived_at`, add archived tab support, and enforce deterministic ordering (including queue-ordered in-progress).

**Architecture:** Keep lifecycle state and archive visibility separate. Persist archive state in `uploads.archived_at`, expose it through platform/API list/detail models, and wire extension archive actions through background messages to a new API endpoint. Apply explicit post-merge sorting in popup rendering.

**Tech Stack:** Python (FastAPI + sqlite), JS (MV3 extension), pytest, node:test

---

### Task 1: Platform Schema + Repository Behavior

**Files:**
- Modify: `passport-platform/src/passport_platform/db.py`
- Modify: `passport-platform/migrations/0001_initial.sql`
- Modify: `passport-platform/src/passport_platform/models/upload.py`
- Modify: `passport-platform/src/passport_platform/schemas/results.py`
- Modify: `passport-platform/src/passport_platform/repositories/uploads.py`
- Modify: `passport-platform/src/passport_platform/repositories/records.py`
- Modify: `passport-platform/src/passport_platform/services/records.py`
- Test: `passport-platform/tests/test_records_service.py`

- [ ] Write failing tests for archived section/list/count behavior and archive toggle behavior in `passport-platform/tests/test_records_service.py`.
- [ ] Run targeted failing tests for platform records service.
- [ ] Implement `archived_at` schema/model/repository/service changes and section semantics (`archived` section; archived rows excluded from pending/submitted/failed counts).
- [ ] Run platform targeted tests until green.

### Task 2: API Contract + Routes

**Files:**
- Modify: `passport-api/src/passport_api/schemas.py`
- Modify: `passport-api/src/passport_api/routes/records.py`
- Modify: `passport-api/tests/test_api.py`
- Modify: `passport-api/README.md`

- [ ] Write failing API tests for:
  - `GET /records?section=archived`
  - `PATCH /records/{upload_id}/archive`
  - archive idempotence/status-agnostic behavior.
- [ ] Run targeted failing API tests.
- [ ] Implement API schema/route updates and response mapping including `archived_at`.
- [ ] Run targeted API tests until green.

### Task 3: Extension Archive Actions + Ordering

**Files:**
- Modify: `passport-masar-extension/strings.js`
- Modify: `passport-masar-extension/popup.html`
- Modify: `passport-masar-extension/popup.js`
- Modify: `passport-masar-extension/background.js`
- Modify: `passport-masar-extension/queue-filter.js`
- Test: `passport-masar-extension/tests/popup.test.js`
- Test: `passport-masar-extension/tests/queue-filter.test.js`
- Test: `passport-masar-extension/tests/background.test.js`

- [ ] Write failing extension tests for:
  - archived tab behavior
  - archive/unarchive message routing
  - immediate selected-id removal on successful archive/unarchive
  - ordering helpers (pending/submitted/failed by created time, archived by archived time, inProgress by queue order).
- [ ] Run targeted failing extension tests.
- [ ] Implement popup/background/tab/strings updates and deterministic sort logic.
- [ ] Run targeted extension tests until green.

### Task 4: End-to-End Verification + Quality Gates

**Files:**
- Modify: `passport-platform/README.md` (if section semantics wording needs sync)
- Modify: `docs/HISTORY.md` (only if a commit is requested later)

- [ ] Run required checks for touched packages from repo root:
  - `uv run ruff check passport-platform/src passport-platform/tests passport-api/src passport-api/tests`
  - `uv run ruff format passport-platform/src passport-platform/tests passport-api/src passport-api/tests`
  - `uv run ty check passport-platform/src passport-api/src`
  - `uv run pytest passport-platform/tests/test_records_service.py passport-api/tests/test_api.py -q`
  - `node --test passport-masar-extension/tests/*.test.js`
- [ ] Confirm no regressions in changed behavior and summarize outcomes with evidence.

