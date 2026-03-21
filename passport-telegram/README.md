# Passport Telegram

`passport-telegram` is the first user-facing adapter for `passport-core`.

It receives passport images from Telegram users, downloads the image bytes, hands the request to `passport-platform` for user/quota/upload orchestration, then runs `passport-core` through that shared processing service. Successful results are returned as one media group that contains:

- the original passport image
- the cropped face image
- an Arabic-first caption with the extracted passport fields formatted for easy copying in Telegram

## Setup

```bash
cd passport-telegram
uv venv --python 3.12
source .venv/bin/activate
uv sync --extra dev
cp .env.example .env
```

Then set:

- `PASSPORT_TELEGRAM_BOT_TOKEN`
- `PASSPORT_TELEGRAM_CORE_ENV_FILE`
- `PASSPORT_TELEGRAM_PLATFORM_ENV_FILE`
- `PASSPORT_TELEGRAM_ADMIN_USER_IDS`
- `PASSPORT_TELEGRAM_ADMIN_USERNAMES`

`PASSPORT_TELEGRAM_CORE_ENV_FILE` should usually point to `../passport-core/.env`.
`PASSPORT_TELEGRAM_PLATFORM_ENV_FILE` should usually point to `../passport-platform/.env`.

That core `.env` must contain the `passport-core` runtime settings, including `PASSPORT_REQUESTY_API_KEY`.
The platform `.env` should contain the shared application database path, such as `PASSPORT_PLATFORM_DB_PATH`.

## Run

```bash
cd passport-telegram
uv run passport-telegram
```

## Production

Build from the workspace root so Docker can copy both sibling packages:

```bash
docker build -f passport-telegram/Dockerfile -t passport-telegram:latest .
```

Prepare a production env file from `.env.production.example`, then run:

```bash
docker run --rm \
  --env-file passport-telegram/.env.production \
  -v passport-telegram-data:/data \
  passport-telegram:latest
```

Notes:

- `PASSPORT_TELEGRAM_CORE_ENV_FILE=/app/passport-core/.env` is used to anchor relative `passport-core` paths inside the container.
- `PASSPORT_TELEGRAM_PLATFORM_ENV_FILE=/app/passport-platform/.env` is used to anchor relative `passport-platform` paths inside the container.
- In production, set the real `PASSPORT_*` values as container env vars instead of relying on a local core `.env` file.
- Mount `/data` to keep stored images, platform state, and SQLite results persistent.

## Behavior

- accepts Telegram photos
- accepts image documents such as `.jpg`, `.jpeg`, `.png`, `.webp`, `.tif`, `.tiff`
- supports media groups by collecting images briefly, then processing them as one batch
- replies in Arabic
- returns each successful result as one two-image media group with an Arabic-first caption
- formats extracted values in the caption for easier copying into منصة نسك forms
- returns partial failure messages when the image is not a passport or when face crop fails
- directs agencies to `@mr3od` or `@naaokun` for clarifications or plan changes
- supports admin commands for usage, recent activity, plan changes, and block/unblock flows

## Environment

- `PASSPORT_TELEGRAM_BOT_TOKEN`: Telegram bot token
- `PASSPORT_TELEGRAM_CORE_ENV_FILE`: path to the `passport-core` `.env`
- `PASSPORT_TELEGRAM_PLATFORM_ENV_FILE`: path to the `passport-platform` `.env`
- `PASSPORT_TELEGRAM_ALLOWED_CHAT_IDS`: optional comma-separated chat ids
- `PASSPORT_TELEGRAM_ADMIN_USER_IDS`: comma-separated admin Telegram user ids, default `552002791,743379791`
- `PASSPORT_TELEGRAM_ADMIN_USERNAMES`: comma-separated admin usernames, used as fallback, default `mr3od,naaokun`
- `PASSPORT_TELEGRAM_ALBUM_COLLECTION_WINDOW_SECONDS`: media-group wait window
- `PASSPORT_TELEGRAM_MAX_IMAGES_PER_BATCH`: safety limit
- `PASSPORT_TELEGRAM_LOG_LEVEL`: default `INFO`

## Development

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
```
