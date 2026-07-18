"""Health-check routes."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.observability.prometheus import READINESS_STATUS
from app.repositories.health import DatabaseHealthRepository
from app.schemas.health import DatabaseHealthResponse, HealthResponse, ReadinessResponse
from app.services.health import HealthService, collect_runtime_readiness

router = APIRouter(prefix="/health", tags=["health"])


async def get_health_service() -> HealthService:
    """Build a liveness-only health service."""

    return HealthService(settings=get_settings())


async def get_database_health_service() -> AsyncGenerator[HealthService, None]:
    """Build a health service with database access."""

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        yield HealthService(
            settings=get_settings(),
            database_repository=DatabaseHealthRepository(db),
        )
    finally:
        db.close()


@router.get("", response_model=HealthResponse)
async def health(service: HealthService = Depends(get_health_service)):
    """Versioned liveness endpoint."""

    return service.application_health()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(
    request: Request,
    service: HealthService = Depends(get_health_service),
):
    """Readiness endpoint for structured bundle availability."""

    READINESS_STATUS.set(0)
    runtime_checks = await collect_runtime_readiness(
        service.settings,
        request.app.state.rate_limiter,
    )
    result = service.readiness_health(runtime_checks)
    if result.status != "ok":
        return JSONResponse(status_code=503, content=result.model_dump())
    READINESS_STATUS.set(1)
    return result


@router.get("/db", response_model=DatabaseHealthResponse)
async def database_health(
    service: HealthService = Depends(get_database_health_service),
):
    """Check PostgreSQL connectivity."""

    return service.database_health()
