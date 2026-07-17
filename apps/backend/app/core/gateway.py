"""Cross-cutting behavior at the FastAPI gateway boundary."""

from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.rate_limit import (
    TokenBucketRateLimiter,
    get_gateway_rate_limit_key,
    get_gateway_rate_limit_policy,
)

logger = logging.getLogger(__name__)


class GatewayMiddleware(BaseHTTPMiddleware):
    """Apply request IDs and throttling at the backend gateway."""

    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()

    async def dispatch(self, request: Request, call_next):
        request_id = getattr(request.state, "request_id", None)
        if not request_id:
            request_id = request.headers.get("X-Request-ID", "").strip()
            request_id = request_id[:128] if request_id else uuid4().hex
        request.state.request_id = request_id

        started_at = perf_counter()
        rate_limit_headers: dict[str, str] = {}

        if self.settings.RATE_LIMIT_ENABLED:
            policy = get_gateway_rate_limit_policy(
                request.method,
                request.url.path,
                self.settings,
            )
            if policy:
                limiter: TokenBucketRateLimiter = request.app.state.rate_limiter
                decision = await limiter.consume(
                    get_gateway_rate_limit_key(request, policy),
                    policy,
                )
                rate_limit_headers = {
                    "X-RateLimit-Policy": policy.name,
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": str(decision.remaining),
                    "X-RateLimit-Reset": str(decision.reset_after),
                }
                if not decision.allowed:
                    elapsed_ms = (perf_counter() - started_at) * 1000
                    logger.warning(
                        "rate limit exceeded",
                        extra={
                            "event": "rate_limit_exceeded",
                            "policy": policy.name,
                            "method": request.method,
                            "path": request.url.path,
                        },
                    )
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": (
                                "Too many requests. Please wait before trying again."
                            ),
                            "request_id": request_id,
                        },
                        headers={
                            **rate_limit_headers,
                            "Retry-After": str(decision.retry_after),
                            "X-Request-ID": request_id,
                            "X-Process-Time-Ms": f"{elapsed_ms:.2f}",
                        },
                    )

        response = await call_next(request)
        elapsed_ms = (perf_counter() - started_at) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        for header, value in rate_limit_headers.items():
            if header not in response.headers:
                response.headers[header] = value
        return response
