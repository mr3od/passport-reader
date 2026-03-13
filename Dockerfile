# Multi-stage build for minimal production image
# Stage 1: Builder - Install dependencies
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy only dependency files first (better layer caching)
COPY passport-core/pyproject.toml passport-core/README.md /build/passport-core/
COPY passport-platform/pyproject.toml passport-platform/README.md /build/passport-platform/
COPY passport-telegram/pyproject.toml passport-telegram/README.md /build/passport-telegram/

# Copy source code
COPY passport-core/src /build/passport-core/src
COPY passport-core/assets /build/passport-core/assets
COPY passport-platform/src /build/passport-platform/src
COPY passport-telegram/src /build/passport-telegram/src

# Create venv and install all packages
RUN uv venv /build/.venv && \
    uv pip install --python /build/.venv/bin/python \
    /build/passport-core \
    /build/passport-platform \
    /build/passport-telegram

# Stage 2: Runtime - Minimal production image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /build/.venv /app/.venv

# Copy source code (needed for editable installs)
COPY --from=builder /build/passport-core/src/passport_core /app/.venv/lib/python3.12/site-packages/passport_core
COPY --from=builder /build/passport-platform/src/passport_platform /app/.venv/lib/python3.12/site-packages/passport_platform

# Copy assets (models, templates)
COPY --from=builder /build/passport-core/assets /app/passport-core/assets

# Create data directories
RUN mkdir -p /data/binaries && \
    chmod -R 755 /data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run as non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /data
USER appuser

CMD ["/app/.venv/bin/python", "-m", "passport_telegram.cli"]
