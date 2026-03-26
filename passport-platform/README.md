# Passport Platform

`passport-platform` is the shared application layer between transport adapters and `passport-core`.

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
cp .env.example .env
uv sync --all-packages
```

## Environment

- `PASSPORT_PLATFORM_DB_PATH`: SQLite database file path
- `PASSPORT_PLATFORM_ARTIFACTS_DIR`: local root for stored upload and face-crop artifacts

## Development

```bash
uv run --package passport-platform pytest passport-platform/tests -q
uv run ruff check passport-platform/src/
```
