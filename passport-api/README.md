# Passport API

`passport-api` is the HTTP adapter for `passport-platform`.

It currently exposes:

- `POST /auth/exchange`
- `GET /me`
- `POST /records/upload`
- `GET /records`
- `GET /records/masar/pending`
- `GET /records/{upload_id}/image`
- `PATCH /records/{upload_id}/masar-status`
- `PATCH /records/{upload_id}/review-status`

## Setup

```bash
# from the repository root
cp .env.example .env
uv sync --all-packages
```

Use the root `.env.example` and copy it to the repository root `.env`.

## Run

```bash
uv run passport-api
```

## Development

```bash
uv run pytest passport-api/tests -q
uv run ruff check passport-api/src passport-api/tests
uv run ty check passport-api/src
```
