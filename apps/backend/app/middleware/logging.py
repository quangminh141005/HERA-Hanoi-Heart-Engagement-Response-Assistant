"""HTTP request logging middleware."""

from __future__ import annotations

import logging
from time import perf_counter

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.request_context import bind_context, normalize_request_id, reset_context

logger = logging.getLogger("app.access")
QUIET_SUCCESS_PATHS = {
    "/health",
    "/healthz",
    "/readyz",
    "/metrics",
    "/api/v1/health",
    "/api/v1/health/ready",
}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log one structured access event per request."""

    async def dispatch(self, request: Request, call_next):
        request_id = getattr(request.state, "request_id", None)
        if not request_id:
            request_id = normalize_request_id(request.headers.get("X-Request-ID"))
            request.state.request_id = request_id

        tokens = bind_context(request_id=request_id, conversation_id=None)
        started_at = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            logger.error(
                "http request failed",
                extra={
                    **_request_log_extra(request, status_code, started_at),
                    "error_type": exc.__class__.__name__,
                },
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
    route = request.scope.get("route")
    route_path = getattr(route, "path", None) or "unmatched"
    return {
        "event": "http_request",
        "method": request.method,
        "route": f"{request.method} {route_path}",
        "status_code": status_code,
        "duration_ms": round((perf_counter() - started_at) * 1000, 2),
    }

