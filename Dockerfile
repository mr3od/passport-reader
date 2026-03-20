# Single image for both passport-telegram and passport-api services.
# Command is overridden per service in docker-compose.yml.
#
#   passport-telegram: runs the Telegram bot
#   passport-api:      runs the FastAPI HTTP server

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN pip install --no-cache-dir uv

# Dependency manifests first — maximises layer cache on source-only changes
COPY passport-core/pyproject.toml     passport-core/README.md     /build/passport-core/
COPY passport-platform/pyproject.toml passport-platform/README.md /build/passport-platform/
COPY passport-telegram/pyproject.toml passport-telegram/README.md /build/passport-telegram/
COPY passport-api/pyproject.toml      passport-api/README.md      /build/passport-api/

# Source
COPY passport-core/src     /build/passport-core/src
COPY passport-core/assets  /build/passport-core/assets
COPY passport-platform/src /build/passport-platform/src
COPY passport-telegram/src /build/passport-telegram/src
COPY passport-api/src      /build/passport-api/src

# Install all four packages into one venv
RUN uv venv /build/.venv && \
    uv pip install --python /build/.venv/bin/python \
        /build/passport-core \
        /build/passport-platform \
        /build/passport-telegram \
        /build/passport-api

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /build/.venv        /app/.venv
COPY --from=builder /build/passport-core/assets /app/assets

RUN mkdir -p /data/artifacts && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /data

USER appuser

# No default CMD — each service in docker-compose.yml provides its own command.
