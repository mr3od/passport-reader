# Passport Reader Workspace

Monorepo workspace for the passport processing system.

## Packages

- `passport-core`: extraction and image-processing engine
- `passport-platform`: shared business logic, persistence, quotas, and orchestration
- `passport-api`: FastAPI adapter
- `passport-telegram`: agency Telegram adapter
- `passport-admin-bot`: admin Telegram adapter
- `passport-benchmark`: evaluation and scoring tools

## Workspace contract

- The maintained workspace is defined by the root `pyproject.toml`.
- Use `uv` from the repository root.
- Use the root `.env` for local development.
- Use the root `.env.production` contract for production.
- Shared tooling is configured at the root:
  - `import-linter`
  - `ruff`
  - `pytest`
  - `ty`

## Setup

```bash
# from the repository root
cp .env.example .env
uv sync --all-packages
```

## Local development

```bash
uv run passport-api
uv run passport-telegram
uv run passport-admin-bot
```

Run package tests from the root:

```bash
uv run pytest passport-admin-bot/tests passport-core/tests passport-platform/tests passport-api/tests passport-telegram/tests passport-benchmark/tests -q
uv run lint-imports
uv run ruff check passport-admin-bot/src passport-core/src passport-platform/src passport-api/src passport-telegram/src passport-benchmark/src
uv run ty check passport-admin-bot/src passport-core/src passport-platform/src passport-api/src passport-telegram/src passport-benchmark/src
```

## Production

- Production targets MicroK8s.
- Kubernetes manifests live under `k8s/`.
- The root `Dockerfile` builds the shared production image.
- CI deploys from the root workspace, enables required MicroK8s addons, applies manifests, and waits for rollout.
