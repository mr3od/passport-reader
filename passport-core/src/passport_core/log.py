from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


class _StructuredFormatter(logging.Formatter):
    def __init__(self, *, json_output: bool) -> None:
        super().__init__()
        self._json_output = json_output

    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key in ("trace_id", "source", "stage", "error_code"):
            value = getattr(record, key, None)
            if value is not None:
                base[key] = value

        if self._json_output:
            return json.dumps(base, ensure_ascii=False)

        extra = " ".join(f"{k}={v}" for k, v in base.items() if k not in {"message", "level"})
        return f"{base['level']} {base['message']} {extra}".strip()


def setup_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_StructuredFormatter(json_output=json_output))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def bind_logger(logger: logging.Logger, **context: str) -> logging.LoggerAdapter[logging.Logger]:
    return logging.LoggerAdapter(logger, context)
