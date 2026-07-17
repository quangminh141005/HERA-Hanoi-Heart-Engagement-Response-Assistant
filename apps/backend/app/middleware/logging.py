"""HTTP request logging middleware."""

from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.request_context import bind_context, reset_context

logger = logging.getLogger("app.access")
QUIET_SUCCESS_PATHS = {"/health", "/metrics"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log one structured access event per request."""

    async def dispatch(self, request: Request, call_next):
        request_id = getattr(request.state, "request_id", None)
        if not request_id:
            request_id = request.headers.get("X-Request-ID", "").strip()
            request_id = request_id[:128] if request_id else uuid4().hex
            request.state.request_id = request_id

        tokens = bind_context(request_id=request_id, conversation_id=None)
        started_at = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.exception(
                "http request failed",
                extra=_request_log_extra(request, status_code, started_at),
            )
            raise
        finally:
            log_extra = _request_log_extra(request, status_code, started_at)
            if _should_log_completed_request(request, status_code):
                logger.info("http request completed", extra=log_extra)
            reset_context(tokens)


def _should_log_completed_request(request: Request, status_code: int) -> bool:
    return not (status_code < 400 and request.url.path in QUIET_SUCCESS_PATHS)


def _request_log_extra(
    request: Request,
    status_code: int,
    started_at: float,
) -> dict[str, object]:
    return {
        "event": "http_request",
        "method": request.method,
        "path": request.url.path,
        "route": f"{request.method} {request.url.path}",
        "status_code": status_code,
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
        "client_host": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }

