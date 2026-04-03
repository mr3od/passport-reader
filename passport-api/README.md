# Passport API

`passport-api` is the HTTP adapter for `passport-platform`.

It currently exposes:

- `POST /auth/exchange`
- `GET /me`
- `POST /records/upload`
- `GET /records`
- `GET /records/counts`
- `GET /records/ids`
- `GET /records/{upload_id}`
- `GET /records/masar/pending`
- `GET /records/{upload_id}/image`
- `PATCH /records/{upload_id}/masar-status`
- `PATCH /records/{upload_id}/review-status`

## Records API notes

- `GET /records` is now the slim workspace list endpoint for the extension.
  - query params:
    - `section`: `pending`, `submitted`, `failed`, `all`
    - `limit`: default `50`, max `100`
    - `offset`: default `0`
  - response shape:
    - `items`
    - `limit`
    - `offset`
    - `total`
    - `has_more`
- `GET /records/counts` returns server-truth counts for:
  - `pending`
  - `submitted`
  - `failed`
- `pending` list/count semantics are extension-workspace semantics:
  - includes processed records that can still be submitted from the main lane
  - `review_status` does not block pending visibility
  - excludes records whose latest submit attempt is already `failed` or `missing`
- `GET /records/ids` is the lightweight submit-eligibility discovery endpoint for the extension bulk-submit flow.
  - query params:
    - `section=pending`
    - `limit`: default `100`, max `100`
    - `offset`: default `0`
  - eligibility matches the main pending lane:
    - `upload_status = processed`
    - latest `masar_status IS NULL`
    - `review_status` does not block bulk submission
- `GET /records/{upload_id}` remains the heavy detail endpoint.
  - this route may still return:
    - `extraction_result`
    - `passport_image_uri`
    - submission context fields
    - failure fields
- list responses intentionally omit heavy fields that are not needed for popup rendering:
  - `extraction_result`
  - `passport_image_uri`
  - `confidence_overall`

- `PATCH /records/{upload_id}/masar-status` currently accepts:
  - `submitted`
  - `failed`
  - `missing`
- record responses expose the latest stored Masar submission context, including:
  - submission entity fields
  - submission contract fields
  - submission group fields
- this allows adapters such as the extension to reopen details or explain prior submission context without querying internal platform state directly

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
