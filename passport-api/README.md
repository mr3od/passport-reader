# Passport API

`passport-api` is the HTTP adapter for `passport-platform`.

It currently exposes:

- `POST /auth/exchange`
- `GET /me`
- `GET /records`

## Setup

```bash
uv sync --all-packages
cp passport-platform/.env.example passport-platform/.env
cp passport-core/.env.example passport-core/.env
cp passport-api/.env.example passport-api/.env
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
