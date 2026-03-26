# Passport Telegram

`passport-telegram` is the agency-facing Telegram adapter for `passport-platform`.

It receives passport images from Telegram users, downloads the image bytes, and hands the request to `passport-platform`. Telegram does not construct or import `passport-core` directly; `passport-platform` owns the shared runtime builders and processing orchestration.

Successful results are returned as a single photo message (the original upload) with an Arabic-first caption that includes:

- extracted passport fields formatted for easy copying
- review status summary
- confidence summary and warning count

## Setup

```bash
# from the repository root
cp .env.example .env
uv sync --all-packages
```

Use the root `.env.example` and copy it to the repository root `.env`.

Then set at least:

- `PASSPORT_TELEGRAM_BOT_TOKEN`
- `PASSPORT_REQUESTY_API_KEY`

The supported local workflow uses the root `.env` only.

## Run

```bash
uv run passport-telegram
```

## Production

Production uses the root `Dockerfile`, root `.env.production`, and the versioned manifests under `k8s/`.

## Environment

- `PASSPORT_TELEGRAM_BOT_TOKEN`: Telegram bot token
- `PASSPORT_TELEGRAM_ALLOWED_CHAT_IDS`: optional comma-separated chat ids
- `PASSPORT_TELEGRAM_ADMIN_USER_IDS`: comma-separated admin Telegram user ids, default `552002791,743379791`
- `PASSPORT_TELEGRAM_ADMIN_USERNAMES`: comma-separated admin usernames, used as fallback, default `mr3od,naaokun`
- `PASSPORT_TELEGRAM_ALBUM_COLLECTION_WINDOW_SECONDS`: media-group wait window
- `PASSPORT_TELEGRAM_MAX_IMAGES_PER_BATCH`: safety limit
- `PASSPORT_TELEGRAM_LOG_LEVEL`: default `INFO`

## Development

```bash
uv run pytest passport-telegram/tests -q
uv run ruff check passport-telegram/src passport-telegram/tests
uv run ty check passport-telegram/src
```
