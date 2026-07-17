"""Structured logging setup."""

from __future__ import annotations

import json
import logging as py_logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.core.request_context import get_context

_RESERVED_LOG_RECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}


class RequestContextFilter(py_logging.Filter):
    """Attach request fields to every log record."""

    def filter(self, record: py_logging.LogRecord) -> bool:
        for key, value in get_context().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class JsonFormatter(py_logging.Formatter):
    """Format logs as single-line JSON."""

    def __init__(self, *, service_name: str, environment: str) -> None:
        super().__init__()
        self.service_name = service_name
        self.environment = environment

    def format(self, record: py_logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=UTC,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "environment": self.environment,
            "request_id": getattr(record, "request_id", None),
            "conversation_id": getattr(record, "conversation_id", None),
        }

        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _RESERVED_LOG_RECORD_ATTRS:
                continue
            if key in payload:
                continue
            payload[key] = _json_safe(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(settings: Settings) -> None:
    """Configure root logging for the backend process."""

    level = getattr(py_logging, settings.LOG_LEVEL.upper(), py_logging.INFO)
    handler = py_logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestContextFilter())
    if settings.LOG_FORMAT == "json":
        handler.setFormatter(
            JsonFormatter(
                service_name=settings.SERVICE_NAME,
                environment=settings.ENVIRONMENT,
            )
        )
    else:
        handler.setFormatter(
            py_logging.Formatter(
                "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
            )
        )

    root_logger = py_logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = py_logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level)
    py_logging.getLogger("uvicorn.access").setLevel(py_logging.WARNING)


def _json_safe(value: Any) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)
