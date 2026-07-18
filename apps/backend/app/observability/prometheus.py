"""Prometheus metrics for the FastAPI backend."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Final

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
REQUESTS_TOTAL = Counter(
    "hera_requests_total",
    "Chat turns by bounded intent and outcome.",
    ("intent", "result"),
)
GROUNDING_FAILURES_TOTAL = Counter(
    "hera_grounding_failures_total",
    "Factual answers withheld because grounding was insufficient.",
    ("reason",),
)
DATA_FRESHNESS_REJECTIONS_TOTAL = Counter(
    "hera_data_freshness_rejections_total",
    "Structured requests rejected by a freshness gate.",
    ("dataset",),
)
SCHEDULE_COVERAGE = Gauge(
    "hera_schedule_coverage",
    "Published schedule-document coverage ratio for a facility and week.",
    ("facility", "week"),
)
SCHEDULE_HORIZON_READY = Gauge(
    "hera_schedule_horizon_ready",
    "Whether the configured schedule horizon is fully published.",
    ("horizon",),
)
BOOKING_HOLDS_TOTAL = Counter(
    "hera_booking_holds_total",
    "Prototype booking hold decisions.",
    ("result",),
)
BOOKING_OCCUPIED = Gauge(
    "hera_booking_occupied",
    "Active held or confirmed places for a canonical booking session.",
    ("session_id",),
)
BOOKING_CAPACITY_LIMIT = Gauge(
    "hera_booking_capacity_limit",
    "Capacity limit for a canonical booking session.",
    ("session_id",),
)
AI_RESPONSES_TOTAL = Counter(
    "hera_ai_responses_total",
    "Assistant responses by safety-grounding outcome.",
    ("response_type", "grounded"),
)
GUARDRAIL_BLOCKS_TOTAL = Counter(
    "hera_guardrail_blocks_total",
    "Input or output guardrail blocks.",
    ("violation_type",),
)
EMERGENCY_HANDOFFS_TOTAL = Counter(
    "hera_emergency_handoffs_total",
    "Emergency handoffs emitted before normal model processing.",
)
DEPENDENCY_UP = Gauge(
    "hera_dependency_up",
    "Whether a runtime dependency passed its most recent readiness probe.",
    ("dependency",),
)
LATENCY_SECONDS = Histogram(
    "hera_latency_seconds",
    "HTTP request latency by bounded route template.",
    ("route",),
)
UPSTREAM_FAILURES_TOTAL = Counter(
    "hera_upstream_failures_total",
    "Failed upstream calls by bounded provider name.",
    ("provider",),
)
UPSTREAM_TIMEOUTS_TOTAL = Counter(
    "hera_upstream_timeouts_total",
    "Timed-out upstream calls by bounded provider name.",
    ("provider",),
)
READINESS_STATUS = Gauge(
    "hera_readiness_status",
    "Whether the complete readiness gate most recently passed.",
)
RELEASE_GATE = Gauge(
    "hera_release_gate",
    "Whether an immutable release/safety gate most recently passed.",
    ("gate",),
)
STRUCTURED_CACHE_OPERATIONS_TOTAL = Counter(
    "hera_structured_cache_operations_total",
    "Approved structured Redis-cache operations by bounded outcome.",
    ("result",),
)
AI_TOKENS_TOTAL = Counter(
    "hera_ai_tokens_total",
    "Provider-reported AI tokens by bounded provider and input/output kind.",
    ("provider", "kind"),
)

_UPSTREAM_PROVIDER_LABELS: Final = frozenset(
    {
        "fpt_llm",
        "fpt_embedding",
        "hospital_booking",
        "hospital_search",
        "openai",
        "rag_pipeline",
    }
)

# Emit zero-valued series before the first event so absence cannot hide a fault.
for _provider in sorted(_UPSTREAM_PROVIDER_LABELS | {"unknown"}):
    UPSTREAM_FAILURES_TOTAL.labels(provider=_provider)
    UPSTREAM_TIMEOUTS_TOTAL.labels(provider=_provider)
for _reason in ("missing_citation", "output_guardrail", "no_structured_match"):
    GROUNDING_FAILURES_TOTAL.labels(reason=_reason)
for _dataset in ("service_price", "bhyt", "schedule"):
    DATA_FRESHNESS_REJECTIONS_TOTAL.labels(dataset=_dataset)
DEPENDENCY_UP.labels(dependency="rate_limit_store").set(0)
DEPENDENCY_UP.labels(dependency="postgresql").set(0)
SCHEDULE_HORIZON_READY.labels(horizon="next_week").set(0)
for _gate in (
    "capacity_safety",
    "database_migration",
    "emergency_template",
    "manifest_integrity",
    "model_configuration",
    "release_metadata",
    "schedule_publication",
):
    RELEASE_GATE.labels(gate=_gate).set(0)
READINESS_STATUS.set(0)
for _result in ("hit", "miss", "write", "skipped", "error"):
    STRUCTURED_CACHE_OPERATIONS_TOTAL.labels(result=_result)
for _provider in ("fpt_llm", "fpt_embedding", "openai", "unknown"):
    for _kind in ("input", "output"):
        AI_TOKENS_TOTAL.labels(provider=_provider, kind=_kind)


def record_ai_usage(
    provider: str,
    *,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Record provider-reported usage without unbounded metric labels."""

    safe_provider = provider if provider in _UPSTREAM_PROVIDER_LABELS else "unknown"
    if input_tokens > 0:
        AI_TOKENS_TOTAL.labels(provider=safe_provider, kind="input").inc(
            input_tokens
        )
    if output_tokens > 0:
        AI_TOKENS_TOTAL.labels(provider=safe_provider, kind="output").inc(
            output_tokens
        )


def record_upstream_failure(provider: str, exc: BaseException) -> None:
    """Record one bounded provider failure and its timeout classification.

    Provider labels must never come from request data. Unknown adapter labels are
    deliberately collapsed so a future integration cannot create an unbounded
    Prometheus series by accident.
    """

    safe_provider = provider if provider in _UPSTREAM_PROVIDER_LABELS else "unknown"
    UPSTREAM_FAILURES_TOTAL.labels(provider=safe_provider).inc()
    if _is_timeout_error(exc):
        UPSTREAM_TIMEOUTS_TOTAL.labels(provider=safe_provider).inc()


def _is_timeout_error(exc: BaseException) -> bool:
    """Recognize SDK and wrapped timeout errors without importing each SDK."""

    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, TimeoutError):
            return True
        class_name = current.__class__.__name__.lower()
        if "timeout" in class_name or "timedout" in class_name:
            return True
        current = current.__cause__ or current.__context__
    return False


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
            LATENCY_SECONDS.labels(route=path).observe(elapsed_seconds)
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
    # Never turn attacker-controlled, unmatched URLs into unbounded labels.
    return "unmatched"

