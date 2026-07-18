"""Privacy-preserving optional Langfuse tracing for HERA."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class NoopObservation:
    """Observation object that accepts update calls without exporting data."""

    def update(self, **kwargs: Any) -> None:
        del kwargs


class SafeObservation:
    """Prevent chat content from entering tracing unless explicitly allowed."""

    def __init__(self, delegate: Any, *, capture_content: bool) -> None:
        self.delegate = delegate
        self.capture_content = capture_content

    def update(self, **kwargs: Any) -> None:
        safe_kwargs = dict(kwargs)
        if not self.capture_content:
            metadata = safe_kwargs.get("metadata")
            safe_kwargs = {
                "metadata": _safe_metadata(metadata)
                if isinstance(metadata, dict)
                else {}
            }
        try:
            self.delegate.update(**safe_kwargs)
        except Exception as exc:
            logger.warning(
                "trace update failed",
                extra={
                    "event": "trace_update_failed",
                    "error_type": exc.__class__.__name__,
                },
            )


@contextmanager
def start_observation(
    name: str,
    *,
    settings: Settings | None = None,
    as_type: str = "span",
    metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Iterator[NoopObservation | SafeObservation]:
    """Start a metadata-only Langfuse observation or degrade to a no-op."""

    active_settings = settings or get_settings()
    client = _client_for(active_settings)
    if client is None:
        yield NoopObservation()
        return

    trace_kwargs = dict(kwargs)
    if not active_settings.LANGFUSE_CAPTURE_CONTENT:
        # Metadata-only means exactly that: do not forward arbitrary Langfuse
        # kwargs such as user_id/session_id/status_message that callers could
        # accidentally fill with patient content.
        trace_kwargs = {}
    try:
        manager = client.start_as_current_observation(
            name=name,
            as_type=as_type,
            metadata=_safe_metadata(metadata or {}),
            **trace_kwargs,
        )
        observation = manager.__enter__()
    except Exception as exc:
        logger.warning(
            "trace start failed; continuing without tracing",
            extra={
                "event": "trace_start_failed",
                "error_type": exc.__class__.__name__,
            },
        )
        yield NoopObservation()
        return

    try:
        yield SafeObservation(
            observation,
            capture_content=active_settings.LANGFUSE_CAPTURE_CONTENT,
        )
    except BaseException:
        error = sys.exc_info()
        try:
            manager.__exit__(*error)
        except Exception as trace_exc:
            logger.warning(
                "trace close failed after application error",
                extra={
                    "event": "trace_close_failed",
                    "error_type": trace_exc.__class__.__name__,
                },
            )
        raise
    else:
        try:
            manager.__exit__(None, None, None)
        except Exception as exc:
            logger.warning(
                "trace close failed",
                extra={
                    "event": "trace_close_failed",
                    "error_type": exc.__class__.__name__,
                },
            )


def flush_tracing(settings: Settings | None = None) -> None:
    """Flush pending observations during graceful application shutdown."""

    client = _client_for(settings or get_settings())
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:
        logger.warning(
            "trace flush failed",
            extra={
                "event": "trace_flush_failed",
                "error_type": exc.__class__.__name__,
            },
        )


def _client_for(settings: Settings):
    if not settings.LANGFUSE_ENABLED:
        return None
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        logger.warning(
            "Langfuse enabled without credentials; tracing disabled",
            extra={"event": "trace_credentials_missing"},
        )
        return None
    return _build_client(
        settings.LANGFUSE_PUBLIC_KEY,
        settings.LANGFUSE_SECRET_KEY,
        settings.LANGFUSE_HOST,
        settings.LANGFUSE_SAMPLE_RATE,
        settings.ENVIRONMENT,
        settings.APP_VERSION,
    )


@lru_cache(maxsize=4)
def _build_client(
    public_key: str,
    secret_key: str,
    host: str,
    sample_rate: float,
    environment: str,
    release: str,
):
    from langfuse import Langfuse

    return Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
        sample_rate=sample_rate,
        environment=environment,
        release=release,
        tracing_enabled=True,
    )


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Allow only small scalar metadata; reject nested content-like payloads."""

    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, str | int | float | bool) or value is None:
            safe[str(key)[:64]] = value if not isinstance(value, str) else value[:256]
    return safe
