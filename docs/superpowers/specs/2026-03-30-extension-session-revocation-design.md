# Extension Session Revocation Design

## Goal

Keep the extension logged in until the user explicitly re-links it, while ensuring that requesting a new extension token immediately invalidates every older extension session for that user.

## Scope

In scope:
- change extension auth from expiring sessions to revocable sessions
- allow only one active extension session per user
- revoke all existing extension sessions during `/auth/exchange`
- remove `expires_at` from extension-session storage, models, and API responses
- update extension popup storage and tests to match the new contract

Out of scope:
- changing temp-token behavior
- adding multi-device session support
- adding refresh tokens
- changing agency-facing bot wording unless the login instructions become incorrect

## Current State

Today the auth flow works like this:
- the Telegram bot issues a one-time temp token
- the extension sends that token to `POST /auth/exchange`
- the platform marks the temp token as used and creates a new extension session
- the extension stores `api_token` and `api_token_expires_at`
- authenticated API routes accept the bearer token only while the session is not revoked and not expired

Problems with the current model:
- agencies are logged out after the session TTL even when they are still using the same extension
- requesting a new temp token does not revoke older active extension sessions
- `api_token_expires_at` adds state the product no longer wants to use
- the extension reset flow clears local storage but does not revoke the server-side session

## Decision

Use a single-active-session-per-user model with no session expiry.

### Temp tokens

Temp tokens remain unchanged:
- one-time use
- short-lived
- exchanged through `POST /auth/exchange`

### Extension sessions

Extension sessions become revocable bearer sessions with no `expires_at`.

Session validity becomes:
- session token exists
- session is not revoked
- user is not blocked

### Exchange behavior

`POST /auth/exchange` should:
- validate the temp token
- mark the temp token as used
- revoke every existing active extension session for the same user
- create one new extension session
- return only the new `session_token`

This makes the newest login authoritative and invalidates all older extension logins immediately.

## Data Model

### Remove session expiry

The `extension_sessions` table should remove the `expires_at` column entirely.

The Python `ExtensionSession` model should contain only:
- `id`
- `user_id`
- `session_token_hash`
- `revoked_at`
- `created_at`

The issued-session schema should no longer include `expires_at`.

### Dev-phase migration strategy

This is a breaking development-phase change. Existing local databases may be reset instead of migrated in place.

Required updates still need to keep the codebase internally consistent:
- update the schema in `passport-platform/src/passport_platform/db.py`
- update the reference SQL in `passport-platform/migrations/0001_initial.sql`
- remove `expires_at` from all extension-session models and schemas

No compatibility layer should keep dead `expires_at` fields around.

## API Contract

### `/auth/exchange`

Request body stays the same:
- `{ "token": "<temp-token>" }`

Response becomes:
- `{ "session_token": "<extension-session-token>" }`

`expires_at` is removed from the response.

### Authenticated routes

All protected API routes keep using bearer authentication.

Authentication should reject sessions only when:
- the bearer token is missing or malformed
- the session token is unknown
- the session is revoked
- the user is blocked

Time-based expiry checks are removed.

## Extension Behavior

The extension popup should:
- exchange the temp token through `/auth/exchange`
- store only `api_token`
- stop storing or reading `api_token_expires_at`
- continue treating `401` or `403` responses as a relink-required state

The existing relink/reset UI may continue to clear local state. A separate server-side logout endpoint is not required for this change because re-linking already revokes prior sessions globally.

## Backend Service Design

`AuthService.exchange_temp_token()` should perform revocation and session creation in one transaction so the handoff is atomic.

Recommended sequence:
1. load and validate the temp token
2. mark the temp token as used
3. revoke all active extension sessions for `token.user_id`
4. create the new extension session
5. return the raw session token

This prevents split state where both the old and new session remain active.

`AuthService.authenticate_session()` should stop checking `expires_at` and should only enforce existence, revocation, and user status.

## Repository Changes

The auth-token repository needs one new operation:
- revoke all active extension sessions for a user at a given timestamp

This should update only sessions whose `revoked_at` is still `NULL`.

The existing single-session revoke method may remain if other callers still need it.

## Testing Plan

### Platform tests

Update and add tests to prove:
- exchanging a temp token returns a session token and marks the temp token used
- exchanging a second temp token for the same user revokes the first extension session
- authenticating with the old revoked session fails
- authenticating with the newest session succeeds
- blocked users are still rejected

Remove or replace tests that assert extension-session expiry behavior.

### API tests

Update API tests to prove:
- `/auth/exchange` returns only `session_token`
- a revoked older bearer token gets `401`
- the newest bearer token still works on `/me` and other protected routes

### Extension tests

Update extension tests to prove:
- `exchangeTempToken()` reads only `session_token`
- the popup stores only `api_token`
- relink-required behavior still triggers on `401` and `403`

## Files Expected To Change

Backend:
- `passport-platform/src/passport_platform/db.py`
- `passport-platform/migrations/0001_initial.sql`
- `passport-platform/src/passport_platform/models/auth.py`
- `passport-platform/src/passport_platform/schemas/auth.py`
- `passport-platform/src/passport_platform/repositories/auth_tokens.py`
- `passport-platform/src/passport_platform/services/auth.py`
- `passport-platform/tests/test_auth_service.py`

API:
- `passport-api/src/passport_api/schemas.py`
- `passport-api/src/passport_api/routes/auth.py`
- `passport-api/src/passport_api/deps.py`
- `passport-api/tests/test_api.py`

Extension:
- `passport-masar-extension/auth.js`
- `passport-masar-extension/popup.js`
- `passport-masar-extension/tests/auth.test.js`

## Risks

### Token theft impact

Removing expiry means a leaked session token remains valid until re-link, explicit revocation, or user blocking. The design accepts this trade-off because the product requirement is stable login with new-login invalidation.

### Partial implementation risk

If `expires_at` is removed from the API but not from models, storage, or tests, the auth contract will become inconsistent. This must be implemented as one complete change.

### Multi-device limitation

The design intentionally allows only one active extension session per user. Logging in from another extension or browser profile will log out the old one.

## Verification Plan

Minimum verification:
- `uv run pytest passport-platform/tests/test_auth_service.py -q`
- `uv run pytest passport-api/tests/test_api.py -q`
- `node --test passport-masar-extension/tests/auth.test.js`

If implementation touches imports or Python package boundaries, also run:
- `uv run lint-imports`
- `uv run ty check passport-platform passport-api`

