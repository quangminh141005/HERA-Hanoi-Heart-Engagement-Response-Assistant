"""Health-check routes."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.repositories.health import DatabaseHealthRepository
from app.schemas.health import DatabaseHealthResponse, HealthResponse
from app.services.health import HealthService

router = APIRouter(prefix="/health", tags=["health"])


async def get_health_service() -> HealthService:
    """Build a liveness-only health service."""

    return HealthService(settings=get_settings())


async def get_database_health_service() -> AsyncGenerator[HealthService, None]:
    """Build a health service with database access."""

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


@router.get("/db", response_model=DatabaseHealthResponse)
async def database_health(
    service: HealthService = Depends(get_database_health_service),
):
    """Check PostgreSQL connectivity."""

    return service.database_health()
