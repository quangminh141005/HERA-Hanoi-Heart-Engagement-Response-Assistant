"""Health-check schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class ReadinessResponse(BaseModel):
    """Readiness response including structured bundle state."""

    status: str
    app: str
    version: str
    environment: str
    structured_bundle_ready: bool
    structured_bundle_path: str
    counts: dict[str, int]
    checks: dict[str, bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    bundle_version: str | None = None
    manifest_sha256: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    reference_date: str | None = None
    last_schedule_date: str | None = None

