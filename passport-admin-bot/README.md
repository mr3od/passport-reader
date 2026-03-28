# Passport Admin Bot

`passport-admin-bot` is the admin/operator Telegram adapter for `passport-platform`.

It exposes operator-only commands for usage reporting, recent uploads, plan changes, and account blocking. It depends on `passport-platform` only and must not import `passport-core`.

## Setup

```bash
# from the repository root
cp .env.example .env
uv sync --all-packages
```

Set at least:

- `PASSPORT_ADMIN_BOT_BOT_TOKEN`

## Run

```bash
uv run passport-admin-bot
```

## Environment

- `PASSPORT_ADMIN_BOT_BOT_TOKEN`: Telegram bot token
- `PASSPORT_ADMIN_BOT_ADMIN_USER_IDS`: comma-separated admin Telegram user ids
- `PASSPORT_ADMIN_BOT_ADMIN_USERNAMES`: comma-separated admin usernames, used as fallback
- `PASSPORT_ADMIN_BOT_LOG_LEVEL`: default `INFO`

## Development

```bash
uv run pytest passport-admin-bot/tests -q
uv run ruff check passport-admin-bot/src passport-admin-bot/tests
uv run ty check passport-admin-bot/src
```
