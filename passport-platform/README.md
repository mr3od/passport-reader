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
- `PASSPORT_PLATFORM_LOG_LEVEL`: logging level

## Database

The package initializes its SQLite schema through `Database.initialize()`.

The top-level `migrations/` directory contains the reference SQL for the initial
schema and indexes.

## Public API

Adapters should depend on services, not repositories.

```python
from passport_platform import (
    Database,
    PlatformSettings,
    ProcessingService,
    QuotaService,
    UploadService,
    UserService,
)
```

## Current Scope

This package currently includes:

- config and SQLite bootstrap
- plan policies
- user registration and lookup
- upload registration
- usage ledger accounting
- monthly quota evaluation
- transport-neutral processing orchestration around `passport-core`

The processing service coordinates:

- user resolution
- quota checks
- upload registration
- `passport-core` workflow execution
- processing result persistence
- usage ledger updates

## Development

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
```
