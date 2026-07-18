"""Cross-cutting behavior at the FastAPI gateway boundary."""

from __future__ import annotations

import logging
import socket
from hashlib import sha256
from time import perf_counter

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.rate_limit import (
    TokenBucketRateLimiter,
    get_gateway_rate_limit_key,
    get_gateway_rate_limit_policy,
)
from app.core.request_context import normalize_request_id
from app.observability.prometheus import DEPENDENCY_UP, READINESS_STATUS

logger = logging.getLogger(__name__)
_REPLICA_ID = sha256(socket.gethostname().encode("utf-8")).hexdigest()[:12]


class GatewayMiddleware(BaseHTTPMiddleware):
    """Apply request IDs and throttling at the backend gateway."""

    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()

    async def dispatch(self, request: Request, call_next):
        request_id = getattr(request.state, "request_id", None)
        if not request_id:
            request_id = normalize_request_id(request.headers.get("X-Request-ID"))
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
                try:
                    decision = await limiter.consume(
                        get_gateway_rate_limit_key(
                            request,
                            policy,
                            trust_proxy_headers=self.settings.TRUST_PROXY_HEADERS,
                            trusted_proxy_cidrs=self.settings.TRUSTED_PROXY_CIDRS,
                        ),
                        policy,
                    )
                except Exception as exc:
                    DEPENDENCY_UP.labels(dependency="rate_limit_store").set(0)
                    READINESS_STATUS.set(0)
                    elapsed_ms = (perf_counter() - started_at) * 1000
                    logger.error(
                        "rate limit store unavailable",
                        extra={
                            "event": "rate_limit_store_unavailable",
                            "policy": policy.name,
                            "error_type": exc.__class__.__name__,
                        },
                    )
                    return JSONResponse(
                        status_code=503,
                        content={
                            "error": {
                                "code": "RATE_LIMIT_STORE_UNAVAILABLE",
                                "message_vi": "Hệ thống đang tạm gián đoạn.",
                                "request_id": request_id,
                                "retryable": True,
                            }
                        },
                        headers={
                            "Retry-After": "5",
                            "X-Request-ID": request_id,
                            "X-HERA-Replica": _REPLICA_ID,
                            "X-Process-Time-Ms": f"{elapsed_ms:.2f}",
                        },
                    )
                DEPENDENCY_UP.labels(dependency="rate_limit_store").set(1)
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
        response.headers["X-HERA-Replica"] = _REPLICA_ID
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        for header, value in rate_limit_headers.items():
            if header not in response.headers:
                response.headers[header] = value
        return response
