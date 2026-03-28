FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock /build/
COPY passport-core/pyproject.toml passport-core/README.md /build/passport-core/
COPY passport-platform/pyproject.toml passport-platform/README.md /build/passport-platform/
COPY passport-api/pyproject.toml passport-api/README.md /build/passport-api/
COPY passport-telegram/pyproject.toml passport-telegram/README.md /build/passport-telegram/
COPY passport-admin-bot/pyproject.toml passport-admin-bot/README.md /build/passport-admin-bot/
COPY passport-benchmark/pyproject.toml passport-benchmark/README.md /build/passport-benchmark/

COPY passport-core/src /build/passport-core/src
COPY passport-core/assets /build/passport-core/assets
COPY passport-platform/src /build/passport-platform/src
COPY passport-api/src /build/passport-api/src
COPY passport-telegram/src /build/passport-telegram/src
COPY passport-admin-bot/src /build/passport-admin-bot/src
COPY passport-benchmark/src /build/passport-benchmark/src

RUN uv sync --all-packages --locked --no-dev --no-editable && \
    /build/.venv/bin/python -c "import passport_admin_bot.cli, passport_api.cli, passport_platform, passport_telegram.cli"

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/passport-core/assets /app/assets

RUN mkdir -p /data/artifacts && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /data

USER appuser
