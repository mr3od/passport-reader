# Passport Platform

`passport-platform` is the shared application layer between transport adapters and
`passport-core`.

It owns:

- users and external identity mapping
- plan policies and quota checks
- upload tracking
- processing audit records
- usage ledger accounting

It does not own:

- Telegram bot handlers
- FastAPI routers
- passport image validation, face detection, or LLM extraction

## Package Role

- `passport-core`: passport processing
- `passport-platform`: shared app services
- `passport-telegram`: Telegram transport adapter
- `passport-api`: HTTP transport adapter

## Setup

```bash
cd passport-platform
uv venv --python 3.12
source .venv/bin/activate
uv sync --extra dev
cp .env.example .env
```

## Environment

- `PASSPORT_PLATFORM_DB_PATH`: SQLite database file path
- `PASSPORT_PLATFORM_ARTIFACT_STORE_BACKEND`: currently `local`
- `PASSPORT_PLATFORM_ARTIFACTS_DIR`: local root for stored upload and face-crop artifacts
- `PASSPORT_PLATFORM_LOG_LEVEL`: logging level

## Database

The package initializes its SQLite schema through `Database.initialize()`.

The top-level `migrations/` directory contains the reference SQL for the initial
schema and indexes.

## Public API

Adapters should depend on services, not repositories.

```python
from passport_platform import (
    build_platform_runtime,
    build_processing_runtime,
)

platform = build_platform_runtime(
    platform_env_file=Path("../passport-platform/.env"),
    platform_root_dir=Path("../passport-platform"),
)
runtime = build_processing_runtime(
    platform_runtime=platform,
    core_env_file=Path("../passport-core/.env"),
    core_root_dir=Path("../passport-core"),
)
```

`TrackedProcessingResult` also exposes adapter-safe accessors for:

- upload filename and image bytes
- face crop bytes
- completion flags
- normalized extracted passport data via `result.extracted_data`

## Current Scope

This package currently includes:

- config and SQLite bootstrap
- plan policies
- user registration and lookup
- upload registration
- local artifact persistence for uploaded images and face crops
- usage ledger accounting
- monthly quota evaluation
- transport-neutral processing orchestration around `passport-core`
- reporting and admin-facing usage summaries

The processing runtime coordinates:

- user resolution
- quota checks
- upload registration
- `passport-core` workflow execution
- processing result persistence
- usage ledger updates

The reporting service provides:

- per-user monthly usage summaries
- global monthly usage totals
- recent upload activity for admin tooling

## Development

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
```
