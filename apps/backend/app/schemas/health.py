"""Health-check schemas."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Application liveness response."""

    status: str
    app: str
    version: str
    environment: str


class DatabaseHealthResponse(BaseModel):
    """Database readiness response."""

    status: str
    database: str
    detail: str | None = None

