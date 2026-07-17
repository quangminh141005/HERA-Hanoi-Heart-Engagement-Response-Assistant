"""Prometheus metrics for the FastAPI backend."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)
from starlette.responses import Response as StarletteResponse

HTTP_REQUESTS_TOTAL = Counter(
    "hera_http_requests_total",
    "Total HTTP requests served by the backend.",
    ("method", "path", "status_code"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "hera_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "path", "status_code"),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "hera_http_requests_in_progress",
    "HTTP requests currently being processed by the backend.",
    ("method",),
)
APP_INFO = Info("hera_app", "Backend application metadata.")


def configure_prometheus(
    app: FastAPI,
    *,
    service_name: str,
    version: str,
    environment: str,
    metrics_path: str = "/metrics",
) -> None:
    """Register Prometheus middleware and expose metrics."""

    normalized_metrics_path = (
        metrics_path if metrics_path.startswith("/") else f"/{metrics_path}"
    )
    APP_INFO.info(
        {
            "service": service_name,
            "version": version,
            "environment": environment,
        }
    )

    @app.middleware("http")
    async def prometheus_metrics_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path == normalized_metrics_path:
            return await call_next(request)

        method = request.method.upper()
        started_at = perf_counter()
        status_code = "500"
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return response
        finally:
            elapsed_seconds = perf_counter() - started_at
            path = _route_template(request)
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                path=path,
                status_code=status_code,
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                path=path,
                status_code=status_code,
            ).observe(elapsed_seconds)
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()

    @app.get(normalized_metrics_path, include_in_schema=False)
    async def metrics() -> StarletteResponse:
        return StarletteResponse(
            generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if route_path:
        root_path = request.scope.get("root_path", "")
        return f"{root_path}{route_path}" if root_path else route_path
    return request.url.path

