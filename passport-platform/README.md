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

## Benchmark Seeder

Seeds benchmark passport records for admin users so you can test the extension without sending real passport images via Telegram.

**Prerequisites:** each admin user must have sent `/start` to the Telegram bot at least once — the seeder looks up existing Telegram users and will skip any that are not yet in the database.

**What it does on every run:**
- Imports all labeled cases from `passport-benchmark/cases/labeled` as processed records (skips already-imported ones)
- Deletes all Masar submission rows for those records so the full submission flow can be re-tested

**Locally:**
```bash
uv run python -m passport_platform.management.seed
```

**On the production server (exec into the running API pod):**
```bash
microk8s kubectl exec -n passport-reader deployment/passport-api -- python -m passport_platform.management.seed
```

**As a one-off k8s Job** (after deploying a new image):
```bash
microk8s kubectl apply -f k8s/seed-job.yaml
microk8s kubectl logs -n passport-reader -l job-name=passport-platform-seed -f
```

The Job self-deletes 10 minutes after completion. To re-run it manually, delete and re-apply:
```bash
microk8s kubectl delete job passport-platform-seed -n passport-reader
microk8s kubectl apply -f k8s/seed-job.yaml
```

**Custom cases directory** (optional):
```bash
uv run python -m passport_platform.management.seed --cases-dir /path/to/cases
```

Admin user IDs are read from `PASSPORT_ADMIN_BOT_ADMIN_USER_IDS` (comma-separated Telegram user IDs, same env var used by the admin bot).

## Development

```bash
uv run pytest passport-platform/tests -q
uv run ruff check passport-platform/src passport-platform/tests
uv run ty check passport-platform/src
```
