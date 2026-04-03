# Passport Platform

`passport-platform` is the shared application layer between transport adapters and `passport-core`.

It owns:

- users and external identity mapping
- plan policies and quota checks
- upload tracking
- processing audit records
- usage ledger accounting
- Masar submission persistence and submission-context history

It does not own:

- Telegram bot handlers
- FastAPI routers
- passport image validation, face detection, or LLM extraction

## Package Role

- `passport-core`: passport processing
- `passport-platform`: shared app services
- `passport-telegram`: Telegram transport adapter
- `passport-api`: HTTP transport adapter

## Current Masar-related responsibility

`passport-platform` owns the persisted Masar submission state for records, including:

- current Masar status
- Masar detail ID
- submission entity context
- submission contract context
- submission group context

These fields are returned through the platform record schemas and can be preserved when a submitted mutamer is later patched to `missing`.

## Slim Records Queries

`passport-platform` now exposes separate lightweight record projections for extension workspace rendering:

- slim list items with:
  - record identity
  - passport number
  - `full_name_ar`
  - `full_name_en`
  - lightweight status fields
  - lightweight failure note fields
- count aggregation for:
  - `pending`
  - `submitted`
  - `failed`
- submit-eligible ID discovery for optimistic bulk submit

These lightweight queries are intentionally separate from the heavy `UserRecord` detail projection. They may read extraction JSON internally to derive flattened names, but they do not expose OCR blobs through the lightweight DTOs.

## Setup

```bash
# from the repository root
cp .env.example .env
uv sync --all-packages
```

Use the root `.env.example` and copy it to the repository root `.env`.

## Environment

- `PASSPORT_PLATFORM_DB_PATH`: SQLite database file path
- `PASSPORT_PLATFORM_ARTIFACTS_DIR`: local root for stored upload and face-crop artifacts

## Development

```bash
uv run pytest passport-platform/tests -q
uv run ruff check passport-platform/src passport-platform/tests
uv run ty check passport-platform/src
```
