# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

Monorepo of six Python packages and one Chrome extension, all built around processing passport images for Yemeni travel agencies.

```
passport-core/          # OCR/ML engine (transport-agnostic)
passport-platform/      # Shared app layer: DB, users, quotas, uploads
passport-api/           # FastAPI HTTP adapter
passport-telegram/      # Agency Telegram bot adapter
passport-admin-bot/     # Admin/operator Telegram bot adapter
passport-benchmark/     # Benchmarking and scoring tools
passport-masar-extension/  # Chrome extension (MV3) — auto-submits records to masar.nusuk.sa
```

**Dependency chain:** `passport-core` ← `passport-platform` ← `passport-api` / `passport-telegram` / `passport-admin-bot`

All Python packages use `uv` for dependency management and `hatchling` as build backend.

## Development Commands

Use the root workspace. Do not rely on package-local virtualenv workflows.

```bash
# From the repository root
uv sync --all-packages

# Run all tests
uv run pytest passport-admin-bot/tests passport-core/tests passport-platform/tests passport-api/tests passport-telegram/tests passport-benchmark/tests -q

# Check architecture boundaries
uv run lint-imports

# Run a single test file
uv run pytest passport-core/tests/test_vision.py

# Run a single test
uv run pytest passport-core/tests/test_vision.py::test_name

# Lint + format
uv run ruff check passport-admin-bot/src passport-core/src passport-platform/src passport-api/src passport-telegram/src passport-benchmark/src
uv run ruff format passport-admin-bot/src passport-core/src passport-platform/src passport-api/src passport-telegram/src passport-benchmark/src

# Run the API server
uv run passport-api

# Run the Telegram bot
uv run passport-telegram

# Run the admin bot
uv run passport-admin-bot
```

**Ruff config** (same across all packages): `line-length = 100`, rules `E F I B UP N A SIM RET PTH`.

## Architecture

### passport-core

Current extraction entry point is `passport_core.extraction.PassportExtractor`.

V2 extraction is a single extractor call that returns `ExtractionResult`, including:
- structured data (`data`)
- image/meta assessment (`meta`)
- programmatic confidence (`confidence`)
- validation warnings (`warnings`)
- usage and trace payloads (`usage`, `message_history_json`)

The removed v1 workflow API (`workflow.py`, `llm.py`, old extraction models) must not be reintroduced.

Config via `Settings` (prefix `PASSPORT_`). Runtime extraction requires Requesty credentials/model env vars (for example `PASSPORT_REQUESTY_API_KEY`, `PASSPORT_LLM_MODEL`, `PASSPORT_REQUESTY_BASE_URL`).

### passport-platform

Shared application layer consumed by both adapters. Never instantiated directly by end-users.

**Database** (`db.py`): SQLite via `Database` class. Call `db.initialize()` at startup — it runs `SCHEMA_SQL` then `INDEX_SQL`. Current v2 baseline uses clean reset semantics; `_upgrade_schema()` is intentionally a no-op.

Two transaction patterns:
- `db.connect()` — read-only / manual commit
- `db.transaction()` — auto-commit/rollback context manager; use `immediate=True` for write contention

**Layer structure** (repository → service → caller):
- Repositories do raw SQL and return dataclass models
- Services own business logic and call repositories
- Adapters (telegram/api) instantiate services and call them

**`ProcessingService`** is the main orchestrator: quota check → reserve upload → store artifact → run `PassportExtractor` → persist full `ExtractionResult` JSON → update ledger.

Review automation in platform:
- `review_status` is computed as `auto` or `needs_review` using confidence and warnings.
- `reviewed` is a manual transition used by adapters before submission.
- submission gating is enforced in platform/api, not only in extension UI.

### passport-api

FastAPI app created by `create_app()` factory in `app.py`. Services are built once via `@lru_cache` in `deps.py`.

Auth flow: Telegram bot issues a one-time temp token → client calls `POST /auth/exchange` → receives a bearer session token → uses it for all subsequent requests.

New routes go in `routes/`, registered in `app.py`. All routes use the `get_authenticated_session` dependency from `deps.py`.

### passport-telegram

Agency-facing self-service bot. `MediaGroupCollector` batches photos sent as Telegram media groups (waits `album_collection_window_seconds` before processing).

Messages are Arabic-first and stay in `messages.py`.
Successful processing replies with a single photo (original upload) and caption (no face-crop media).

### passport-admin-bot

Admin/operator Telegram bot. It exposes reporting and account-management commands and must depend on `passport-platform` only.

Messages are English and stay inside the package.

### passport-masar-extension (Chrome MV3)

Background service worker (`background.js`) does everything — no content script needed.

**Header capture**: `webRequest.onSendHeaders` passively captures `activeentityid`, `activeentitytypeid`, `contractid` from any outgoing masar request and persists them to `chrome.storage.local`. These are required for all masar API calls.

**6-step submission flow** (all endpoints under `https://masar.nusuk.sa/umrah/groups_apis/api/`):
1. `POST Mutamer/ScanPassport` — multipart upload, response at `response.data.passportResponse`
2. `POST Mutamer/SubmitPassportInforamtionWithNationality` — note the typo in endpoint name; names sent as `{en, ar}` objects; response `data.id` = mutamerId
3. `POST /umrah/common_apis/api/Attachment/Upload` — vaccination image; response at `data.attachmentResponse.id`
4. `POST Mutamer/GetPersonalAndContactInfos?Id=` — fetch server-assigned picture IDs before step 4
5. `POST Mutamer/SubmitPersonalAndContactInfos` — field is `martialStatusId` (masar's typo, not `maritalStatusId`); phone sent twice as `phone.{countryCode,phoneNumber}` and `mobileCountryKey`/`mobileNo`
6. `POST Mutamer/SubmitDisclosureForm` — field is `muamerInformationId`; 16 questions each need `{questionId, answer, simpleReason, detailedAnswers}`; questions 12 and 13 require placeholder `detailedAnswers` arrays even when `answer: false`

All API responses are wrapped: `{ response: { data: { ... } } }`.

## Schema Changes

Current v2 baseline is clean-reset oriented:
1. Update `passport-platform/src/passport_platform/db.py` (`SCHEMA_SQL` and `INDEX_SQL`)
2. Keep `passport-platform/migrations/*.sql` in sync as the baseline reference
3. Reset local DB files before running when schema changes are not backward-compatible

When adding/changing result fields, update all linked layers together:
- `ProcessingResult` (`models/upload.py`)
- platform result schemas (`schemas/results.py`)
- repository SELECT projections (`repositories/records.py`)
- platform services and API response schemas/routes

## Environment Files

The workspace uses one root `.env.example` for local development and one root `.env.production.example`
for production. Run adapters from the repository root so `passport-core`, `passport-platform`,
`passport-api`, `passport-telegram`, and `passport-admin-bot` all read the same env contract.

## Docker

```bash
# Shared production image
docker build -t passport-reader:latest .
```

The root `Dockerfile` builds the shared production image used by API, agency Telegram, and admin Telegram workloads.
Production deploys through the root `k8s/` manifests on MicroK8s.
