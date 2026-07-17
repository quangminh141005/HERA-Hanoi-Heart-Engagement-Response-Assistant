"""Application health services."""

from __future__ import annotations

from app.core.config import Settings
from app.repositories.health import DatabaseHealthRepository
from app.schemas.health import DatabaseHealthResponse, HealthResponse


class HealthService:
    """Readiness and liveness checks."""

    def __init__(
        self,
        settings: Settings,
        database_repository: DatabaseHealthRepository | None = None,
    ):
        self.settings = settings
        self.database_repository = database_repository

    def application_health(self) -> HealthResponse:
        """Return process-level liveness."""

        return HealthResponse(
            status="ok",
            app=self.settings.APP_NAME,
            version=self.settings.APP_VERSION,
            environment=self.settings.ENVIRONMENT,
        )

    def database_health(self) -> DatabaseHealthResponse:
        """Return database connectivity status."""

        if self.database_repository is None:
            return DatabaseHealthResponse(
                status="error",
                database="postgresql",
                detail="Database repository is not configured.",
            )

        try:
            healthy = self.database_repository.ping()
        except Exception as exc:
            return DatabaseHealthResponse(
                status="error",
                database="postgresql",
                detail=str(exc),
            )
        return DatabaseHealthResponse(
            status="ok" if healthy else "error",
            database="postgresql",
            detail=None if healthy else "SELECT 1 did not return 1.",
        )

