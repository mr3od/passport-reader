FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY passport-core /app/passport-core
COPY passport-platform /app/passport-platform
COPY passport-telegram /app/passport-telegram

RUN uv venv /app/.venv
RUN uv pip install --python /app/.venv/bin/python /app/passport-core /app/passport-platform /app/passport-telegram

WORKDIR /app/passport-telegram

CMD ["/app/.venv/bin/passport-telegram"]
