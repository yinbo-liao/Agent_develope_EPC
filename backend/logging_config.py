"""
Structured logging configuration using Python's built-in logging.

Produces JSON-formatted logs for production log aggregation (ELK, Loki, etc.)
and human-readable logs for development.

Configuration is read directly from the environment (FPSO_LOG_FORMAT,
FPSO_LOG_LEVEL) so this module never imports ``config`` and cannot create an
import cycle:

    FPSO_LOG_FORMAT=json   # json | text (default: text)
    FPSO_LOG_LEVEL=INFO    # standard logging level name (default: INFO)

Any keyword passed to ``logger.info(..., extra={...})`` is emitted as a
top-level JSON field, except for the reserved LogRecord internals. The request
correlation ID (set by middleware.observability) is emitted as
``correlation_id``.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


# Attributes that ``logging.LogRecord`` (and ``logging.Formatter``) already use.
# Anything else found on ``record.__dict__`` came from ``extra=`` and is safe to
# emit as a structured field.
_RESERVED_ATTRS = frozenset({
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",  # Python 3.12+
    "message",
    "asctime",
})

# Canonical top-level keys. Extras must never overwrite these, otherwise the
# JSON object could contain duplicate/inconsistent values.
_CANONICAL_KEYS = frozenset({"timestamp", "level", "logger", "message"})


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for machine-readable logs."""

    def format(self, record: logging.LogRecord) -> str:
        # 1. Start with caller-supplied structured fields.
        extras: dict[str, Any] = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_ATTRS and key not in _CANONICAL_KEYS
        }

        # 2. Overlay the canonical fields so extras cannot spoof them.
        log_entry: dict[str, Any] = dict(extras)
        log_entry.update({
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        })

        # 3. Exception / stack information.
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_entry["stack"] = self.formatStack(record.stack_info)

        # 4. Never let a non-serialisable extra break logging.
        return json.dumps(log_entry, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Human-readable formatter that still surfaces the correlation ID."""

    def __init__(self) -> None:
        super().__init__(
            "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        correlation_id = getattr(record, "correlation_id", None)
        if not correlation_id:
            return super().format(record)

        original_msg, original_args = record.msg, record.args
        try:
            message = record.getMessage()
            record.msg = "[cid=%s] %s" % (correlation_id, message)
            record.args = ()
            return super().format(record)
        finally:
            record.msg = original_msg
            record.args = original_args


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def setup_logging() -> None:
    """Configure application-wide structured logging (idempotent)."""
    log_format = _env("FPSO_LOG_FORMAT", "text").lower()
    log_level = _env("FPSO_LOG_LEVEL", "INFO").upper()

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Idempotent: repeated calls (tests, reloads) must not duplicate output.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # pragma: no cover - defensive
            pass

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if log_format == "json" else TextFormatter())
    root_logger.addHandler(handler)

    # Quiet noisy third-party libraries in production logs.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("redis").setLevel(logging.WARNING)

    logging.getLogger("fpso").info(
        "Logging configured (format=%s, level=%s)", log_format, log_level
    )
