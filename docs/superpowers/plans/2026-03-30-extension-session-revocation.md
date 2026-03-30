# Extension Session Revocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace expiring extension sessions with a single active revocable session per user and remove `expires_at` from the session contract end to end.

**Architecture:** The platform auth service will revoke all prior extension sessions for a user during `/auth/exchange`, then create a single new bearer session with no expiry field. API schemas and extension storage will be simplified to `session_token`/`api_token` only, with relink triggered by backend `401` responses rather than generic auth-state heuristics.

**Tech Stack:** Python workspace with `uv`, FastAPI, SQLite repositories, pytest, Node test runner, Chrome extension popup/auth JS

---

### Task 1: Platform Session Model And Service

**Files:**
- Modify: `passport-platform/src/passport_platform/db.py`
- Modify: `passport-platform/migrations/0001_initial.sql`
- Modify: `passport-platform/src/passport_platform/models/auth.py`
- Modify: `passport-platform/src/passport_platform/schemas/auth.py`
- Modify: `passport-platform/src/passport_platform/repositories/auth_tokens.py`
- Modify: `passport-platform/src/passport_platform/services/auth.py`
- Test: `passport-platform/tests/test_auth_service.py`

- [ ] **Step 1: Write the failing platform tests**

Add tests proving a second exchange revokes the first session and that issued sessions no longer expose `expires_at`.

- [ ] **Step 2: Run platform tests to verify the new cases fail**

Run: `uv run pytest passport-platform/tests/test_auth_service.py -q`

- [ ] **Step 3: Implement the minimal platform changes**

Remove `expires_at` from extension session schema/model/repository rows, add a repository method to revoke all active sessions for a user, and update `exchange_temp_token()`/`authenticate_session()` to use revocation-only validity.

- [ ] **Step 4: Run platform tests to verify they pass**

Run: `uv run pytest passport-platform/tests/test_auth_service.py -q`

### Task 2: API Contract Cleanup

**Files:**
- Modify: `passport-api/src/passport_api/schemas.py`
- Modify: `passport-api/src/passport_api/routes/auth.py`
- Modify: `passport-api/tests/test_api.py`

- [ ] **Step 1: Write the failing API tests**

Update API tests so `/auth/exchange` returns only `session_token`, and add a case where a second exchange makes the first bearer token fail with `401`.

- [ ] **Step 2: Run API tests to verify the new cases fail**

Run: `uv run pytest passport-api/tests/test_api.py -q`

- [ ] **Step 3: Implement the minimal API changes**

Remove `expires_at` from the response schema and route payload shape, then keep protected route auth behavior aligned with the platform service.

- [ ] **Step 4: Run API tests to verify they pass**

Run: `uv run pytest passport-api/tests/test_api.py -q`

### Task 3: Extension Auth Flow Cleanup

**Files:**
- Modify: `passport-masar-extension/auth.js`
- Modify: `passport-masar-extension/popup.js`
- Test: `passport-masar-extension/tests/auth.test.js`

- [ ] **Step 1: Write the failing extension tests**

Update extension tests so exchange consumes only `session_token` and no longer expects `expiresAt`.

- [ ] **Step 2: Run extension tests to verify the new cases fail**

Run: `node --test passport-masar-extension/tests/auth.test.js`

- [ ] **Step 3: Implement the minimal extension changes**

Remove `expiresAt` handling from auth exchange and popup storage so only `api_token` is persisted.

- [ ] **Step 4: Run extension tests to verify they pass**

Run: `node --test passport-masar-extension/tests/auth.test.js`

### Task 4: Workspace Verification

**Files:**
- Modify: `docs/HISTORY.md`

- [ ] **Step 1: Run Python formatting and lint checks**

Run: `uv run ruff check passport-platform passport-api`

- [ ] **Step 2: Run Python formatting**

Run: `uv run ruff format passport-platform passport-api`

- [ ] **Step 3: Run import boundary check**

Run: `uv run lint-imports`

- [ ] **Step 4: Run type checks**

Run: `uv run ty check passport-platform passport-api`

- [ ] **Step 5: Run focused test suite**

Run: `uv run pytest passport-platform/tests/test_auth_service.py passport-api/tests/test_api.py -q`

- [ ] **Step 6: Run extension tests**

Run: `node --test passport-masar-extension/tests/auth.test.js`

- [ ] **Step 7: Update history**

Append a short entry to `docs/HISTORY.md` describing the auth contract change and mark the agent as `[codex]`.
