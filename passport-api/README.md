# Passport API

`passport-api` is the HTTP adapter for `passport-platform`.

It currently exposes:

- `POST /auth/exchange`
- `GET /me`
- `GET /records`

## Setup

```bash
cp .env.example .env
uv sync --all-packages
```

## Run

```bash
uv run passport-api
```

## Development

```bash
uv run --package passport-api pytest passport-api/tests -q
uv run ruff check passport-api/src/
```
