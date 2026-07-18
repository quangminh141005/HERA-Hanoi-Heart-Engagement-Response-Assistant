"""Main FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.observability.tracing import flush_tracing
from app.api_gateway import register_api_gateway
from app.core.config import get_settings
from app.core.errors import HeraApiError
from app.core.gateway import GatewayMiddleware
from app.core.logging import configure_logging
from app.core.rate_limit import create_rate_limiter
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.utf8_json import Utf8JsonContentTypeMiddleware
from app.observability.prometheus import READINESS_STATUS
from app.routers.chat import close_chat_service
from app.routers.structured import close_structured_service
from app.services.health import HealthService, collect_runtime_readiness

settings = get_settings()
configure_logging(settings)
rate_limiter = create_rate_limiter(settings)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialize process-scoped services before serving requests."""

    application.state.rate_limiter = rate_limiter
    await rate_limiter.startup()
    logger.info(
        "backend started",
        extra={
            "event": "application_startup",
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        },
    )
    try:
        yield
    finally:
        await close_chat_service()
        close_structured_service()
        await rate_limiter.close()
        flush_tracing(settings)
        logger.info("backend stopped", extra={"event": "application_shutdown"})


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Customer-care assistant API for Hanoi Heart Hospital. "
        "This service is not a medical diagnosis system."
    ),
    lifespan=lifespan,
)
app.state.rate_limiter = rate_limiter

app.add_middleware(Utf8JsonContentTypeMiddleware)
app.add_middleware(GatewayMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

if settings.PROMETHEUS_METRICS_ENABLED:
    try:
        from app.observability.prometheus import configure_prometheus

        configure_prometheus(
            app,
            service_name=settings.SERVICE_NAME,
            version=settings.APP_VERSION,
            environment=settings.ENVIRONMENT,
            metrics_path=settings.PROMETHEUS_METRICS_PATH,
        )
    except ModuleNotFoundError:
        logger.warning(
            "prometheus metrics disabled because dependency is missing",
            extra={"event": "prometheus_dependency_missing"},
        )


@app.get("/health")
async def root_health_check():
    """Unversioned liveness endpoint for platforms and load balancers."""

    return HealthService(settings=settings).application_health()


@app.get("/healthz")
async def healthz():
    """Preferred liveness endpoint for deployment probes."""

    return HealthService(settings=settings).application_health()


@app.get("/readyz")
async def readyz():
    """Preferred readiness endpoint for deployment probes."""

    READINESS_STATUS.set(0)
    runtime_checks = await collect_runtime_readiness(
        settings,
        rate_limiter,
    )
    result = HealthService(settings=settings).readiness_health(runtime_checks)
    if result.status != "ok":
        return JSONResponse(status_code=503, content=result.model_dump())
    READINESS_STATUS.set(1)
    return result


register_api_gateway(app)


@app.exception_handler(HeraApiError)
async def hera_api_error_handler(request: Request, exc: HeraApiError):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.info(
        "expected API decision",
        extra={
            **_request_error_extra(request, exc.status_code),
            "event": "api_decision",
            "result_code": exc.code,
            "retryable": exc.retryable,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message_vi": exc.message_vi,
                "request_id": request_id,
                "retryable": exc.retryable,
            }
        },
    )


def _request_error_extra(request: Request, status_code: int) -> dict[str, object]:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None) or "unmatched"
    return {
        "event": "http_exception",
        "method": request.method,
        "route": f"{request.method} {route_path}",
        "status_code": status_code,
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Log handled HTTP exceptions and return a stable error shape."""

    logger.warning(
        "http exception",
        extra={
            **_request_error_extra(request, exc.status_code),
            "detail_type": type(exc.detail).__name__,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """Log request validation errors without dumping request bodies."""

    safe_errors = [
        {
            "type": item.get("type"),
            "loc": item.get("loc"),
            "msg": item.get("msg"),
        }
        for item in exc.errors()
    ]
    logger.warning(
        "request validation failed",
        extra={
            **_request_error_extra(request, 422),
            "event": "request_validation_error",
            "errors": safe_errors,
        },
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_FAILED",
                "message_vi": "Dữ liệu gửi lên không hợp lệ.",
                "request_id": getattr(request.state, "request_id", "unknown"),
                "retryable": False,
                "fields": safe_errors,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log an opaque error type without serializing exception/user content."""

    logger.error(
        "unhandled exception",
        extra={
            **_request_error_extra(request, 500),
            "event": "unhandled_exception",
            "error_type": exc.__class__.__name__,
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

