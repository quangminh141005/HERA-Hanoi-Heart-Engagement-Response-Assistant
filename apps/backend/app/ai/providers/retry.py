"""Small retry helpers for idempotent model-provider calls."""

from __future__ import annotations

import asyncio
import email.utils
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_RETRYABLE_STATUS_CODES = {429, 502, 503}
_TIMEOUT_CLASS_NAMES = {
    "TimeoutError",
    "APITimeoutError",
    "TimeoutException",
    "ReadTimeout",
    "ConnectTimeout",
}
_CONNECTION_CLASS_NAMES = {
    "APIConnectionError",
    "ConnectError",
    "ConnectionError",
    "NetworkError",
}


async def retry_provider_call(
    operation: Callable[[], Awaitable[T]],
    *,
    label: str,
    max_attempts: int,
    base_delay_seconds: float,
    max_delay_seconds: float,
    retry_timeouts: bool,
) -> T:
    """Retry transient pre-execution/provider failures with jitter."""

    attempts = max(1, max_attempts)
    for attempt in range(attempts):
        try:
            return await operation()
        except Exception as exc:
            if attempt >= attempts - 1 or not _is_retryable(
                exc,
                retry_timeouts=retry_timeouts,
            ):
                raise
            delay = _retry_after_seconds(exc)
            if delay is None:
                delay = _jittered_backoff(
                    attempt,
                    base_delay_seconds=base_delay_seconds,
                    max_delay_seconds=max_delay_seconds,
                )
            logger.warning(
                "provider call retrying after transient failure",
                extra={
                    "event": "provider_retry",
                    "provider": label,
                    "attempt": attempt + 1,
                    "max_attempts": attempts,
                    "delay_seconds": round(delay, 3),
                    "error_type": exc.__class__.__name__,
                },
            )
            await asyncio.sleep(delay)

    raise RuntimeError("unreachable provider retry state")


def _is_retryable(exc: Exception, *, retry_timeouts: bool) -> bool:
    status_code = _status_code(exc)
    if status_code is not None:
        return status_code in _RETRYABLE_STATUS_CODES
    class_name = exc.__class__.__name__
    if retry_timeouts and class_name in _TIMEOUT_CLASS_NAMES:
        return True
    return class_name in _CONNECTION_CLASS_NAMES


def _status_code(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    if isinstance(value, int):
        return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = None
    try:
        raw = headers.get("Retry-After")
    except Exception:
        return None
    if not raw:
        return None
    try:
        seconds = float(raw)
        return max(0.0, seconds)
    except ValueError:
        pass
    try:
        retry_at = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


def _jittered_backoff(
    attempt: int,
    *,
    base_delay_seconds: float,
    max_delay_seconds: float,
) -> float:
    capped = min(max_delay_seconds, base_delay_seconds * (2**attempt))
    return random.random() * max(0.0, capped)
