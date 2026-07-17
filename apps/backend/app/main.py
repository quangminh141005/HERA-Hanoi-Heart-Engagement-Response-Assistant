"""Main FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api_gateway import register_api_gateway
from app.core.config import get_settings
from app.core.gateway import GatewayMiddleware
from app.core.logging import configure_logging
from app.core.rate_limit import create_rate_limiter
from app.middleware.logging import RequestLoggingMiddleware
from app.observability.prometheus import configure_prometheus
from app.services.health import HealthService

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
        await rate_limiter.close()
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
    configure_prometheus(
        app,
        service_name=settings.SERVICE_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        metrics_path=settings.PROMETHEUS_METRICS_PATH,
    )


@app.get("/health")
async def root_health_check():
    """Unversioned liveness endpoint for platforms and load balancers."""

    return HealthService(settings=settings).application_health()


register_api_gateway(app)


def _request_error_extra(request: Request, status_code: int) -> dict[str, object]:
    return {
        "event": "http_exception",
        "method": request.method,
        "path": request.url.path,
        "route": f"{request.method} {request.url.path}",
        "status_code": status_code,
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Log handled HTTP exceptions and return a stable error shape."""

    logger.warning(
        "http exception",
        extra={
            **_request_error_extra(request, exc.status_code),
            "detail": exc.detail,
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

    logger.warning(
        "request validation failed",
        extra={
            **_request_error_extra(request, 422),
            "event": "request_validation_error",
            "errors": exc.errors(),
        },
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log unexpected exceptions with stack traces."""

    logger.exception(
        "unhandled exception",
        extra={
            **_request_error_extra(request, 500),
            "event": "unhandled_exception",
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

