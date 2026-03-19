# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

Monorepo of four Python packages and one Chrome extension, all built around processing passport images for Yemeni travel agencies.

```
passport-core/          # OCR/ML engine (transport-agnostic)
passport-platform/      # Shared app layer: DB, users, quotas, uploads
passport-telegram/      # Telegram bot adapter
passport-api/           # FastAPI HTTP adapter
passport-masar-extension/  # Chrome extension (MV3) — auto-submits records to masar.nusuk.sa
```

**Dependency chain:** `passport-core` ← `passport-platform` ← `passport-telegram` / `passport-api`

All Python packages use `uv` for dependency management and `hatchling` as build backend.

## Development Commands

Each package has its own virtual environment. Work from inside the package directory.

```bash
# Install a package with dev dependencies
cd passport-core
uv sync --extra dev

# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/test_workflow.py

# Run a single test
uv run pytest tests/test_workflow.py::test_name

# Lint + format
uv run ruff check src/
uv run ruff format src/

# Run the API server
cd passport-api
uv run passport-api

# Run the Telegram bot
cd passport-telegram
uv run passport-telegram
```

**Ruff config** (same across all packages): `line-length = 100`, rules `E F I B UP N A SIM RET PTH`.

## Architecture

### passport-core

Stateless processing pipeline. Entry point is `PassportWorkflow.process_bytes(image_bytes)` → `PassportWorkflowResult`.

Three stages:
1. **Vision** (`vision.py`) — validates passport presence, detects and crops face using ONNX RetinaFace model
2. **LLM extraction** (`llm.py`) — `PassportExtractor` sends the image to an LLM via Requesty router and returns structured `PassportData`
3. **Result assembly** — combines vision + LLM outputs into `PassportWorkflowResult`

Config via `Settings` (prefix `PASSPORT_`). Requires `PASSPORT_REQUESTY_API_KEY` and model-related env vars. Assets (ONNX model, template image) must exist at paths defined in settings.

### passport-platform

Shared application layer consumed by both adapters. Never instantiated directly by end-users.

**Database** (`db.py`): SQLite via `Database` class. Call `db.initialize()` at startup — it runs `SCHEMA_SQL`, calls `_upgrade_schema()` for additive column migrations, then `INDEX_SQL`. Schema upgrades are done inline in `_upgrade_schema()` (not via migration files — the `.sql` files in `migrations/` are reference only).

Two transaction patterns:
- `db.connect()` — read-only / manual commit
- `db.transaction()` — auto-commit/rollback context manager; use `immediate=True` for write contention

**Layer structure** (repository → service → caller):
- Repositories do raw SQL and return dataclass models
- Services own business logic and call repositories
- Adapters (telegram/api) instantiate services and call them

**`ProcessingService`** is the main orchestrator: quota check → reserve upload → store artifact → run `PassportWorkflow` → persist result → update ledger.

### passport-api

FastAPI app created by `create_app()` factory in `app.py`. Services are built once via `@lru_cache` in `deps.py`.

Auth flow: Telegram bot issues a one-time temp token → client calls `POST /auth/exchange` → receives a bearer session token → uses it for all subsequent requests.

New routes go in `routes/`, registered in `app.py`. All routes use the `get_authenticated_session` dependency from `deps.py`.

### passport-telegram

Single-file bot (`bot.py`). `MediaGroupCollector` batches photos sent as Telegram media groups (waits `album_collection_window_seconds` before processing). The bot loads both `passport-core` and `passport-platform` env files at startup via `python-dotenv`.

Messages are Arabic-first; all user-facing strings are in `messages.py`.

### passport-masar-extension (Chrome MV3)

Background service worker (`background.js`) does everything — no content script needed.

**Header capture**: `webRequest.onSendHeaders` passively captures `activeentityid`, `activeentitytypeid`, `contractid` from any outgoing masar request and persists them to `chrome.storage.local`. These are required for all masar API calls.

**5-step submission flow** (all endpoints under `https://masar.nusuk.sa/umrah/groups_apis/api/`):
1. `POST Mutamer/ScanPassport` — multipart upload, response at `response.data.passportResponse`
2. `POST Mutamer/SubmitPassportInforamtionWithNationality` — note the typo in endpoint name; names sent as `{en, ar}` objects; response `data.id` = mutamerId
3. `POST /umrah/common_apis/api/Attachment/Upload` — vaccination image; response at `data.attachmentResponse.id`
4. `POST Mutamer/GetPersonalAndContactInfos?Id=` — fetch server-assigned picture IDs before step 4
5. `POST Mutamer/SubmitPersonalAndContactInfos` — field is `martialStatusId` (masar's typo, not `maritalStatusId`); phone sent twice as `phone.{countryCode,phoneNumber}` and `mobileCountryKey`/`mobileNo`
6. `POST Mutamer/SubmitDisclosureForm` — field is `muamerInformationId`; 16 questions each need `{questionId, answer, simpleReason, detailedAnswers}`; questions 12 and 13 require placeholder `detailedAnswers` arrays even when `answer: false`

All API responses are wrapped: `{ response: { data: { ... } } }`.

## Schema Changes

New columns go in two places:
1. `passport-platform/src/passport_platform/db.py` — add `ALTER TABLE` in `_upgrade_schema()` so existing DBs upgrade automatically on next startup
2. The `.sql` migration files in `passport-platform/migrations/` — for reference/documentation

The `ProcessingResult` dataclass (`models/upload.py`), `UserRecord` schema (`schemas/results.py`), repository SELECT queries (`repositories/records.py`), the platform service, and the API schema/route all need updating together when adding columns.

## Environment Files

Each package has a `.env.example`. The platform and telegram packages point to each other via env file path settings:

```
PASSPORT_TELEGRAM_CORE_ENV_FILE=../passport-core/.env
PASSPORT_TELEGRAM_PLATFORM_ENV_FILE=../passport-platform/.env
PASSPORT_API_PLATFORM_ENV_FILE=../passport-platform/.env   # (ApiSettings.platform_env_file)
```

## Docker

```bash
# Telegram bot image (production)
docker build -f Dockerfile -t passport-telegram:latest .
docker run --env-file .env.production -v passport-data:/data passport-telegram:latest

# API image (separate, not in root Dockerfile)
cd passport-api && docker build -t passport-api:latest .
```

The root `Dockerfile` builds the Telegram bot. Data volume at `/data` must be persistent.
