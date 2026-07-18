"""Application health services."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.observability.prometheus import (
    BOOKING_CAPACITY_LIMIT,
    BOOKING_OCCUPIED,
    DEPENDENCY_UP,
    RELEASE_GATE,
    SCHEDULE_COVERAGE,
    SCHEDULE_HORIZON_READY,
)
from app.repositories.health import (
    EXPECTED_DATABASE_REVISION,
    DatabaseHealthRepository,
)
from app.schemas.health import DatabaseHealthResponse, HealthResponse, ReadinessResponse
from app.structured.postgres_repository import (
    PostgresStructuredRepository,
    StructuredReadRepository,
)

logger = logging.getLogger(__name__)


class HealthService:
    """Readiness and liveness checks."""

    def __init__(
        self,
        settings: Settings,
        database_repository: DatabaseHealthRepository | None = None,
        structured_repository: StructuredReadRepository | None = None,
    ):
        self.settings = settings
        self.database_repository = database_repository
        approval_statuses = (
            ("approved_for_production",)
            if settings.ENVIRONMENT.lower() == "production"
            else ("approved_for_hackathon", "approved_for_production")
        )
        self.structured_repository = (
            structured_repository
            or PostgresStructuredRepository(approval_statuses=approval_statuses)
        )

    def application_health(self) -> HealthResponse:
        """Return process-level liveness."""

        return HealthResponse(
            status="ok",
            app=self.settings.APP_NAME,
            version=self.settings.APP_VERSION,
            environment=self.settings.ENVIRONMENT,
        )

    def readiness_health(
        self,
        runtime_checks: dict[str, bool] | None = None,
    ) -> ReadinessResponse:
        """Validate the release bundle, database and configured embedding index."""

        checks = {
            "structured_database": False,
            "manifest_integrity": False,
            "approval_lane": False,
            "required_data": False,
            "embedding_index": False,
            "booking_sessions": False,
            "emergency_template": False,
            "release_metadata": False,
            "schedule_publication": False,
            "capacity_safety": False,
            "model_configuration": _model_configuration_ready(self.settings),
            "rate_limit_store": False,
            "postgresql": False,
            "database_migration": False,
        }
        checks.update(runtime_checks or {})
        for gate in (
            "capacity_safety",
            "database_migration",
            "emergency_template",
            "manifest_integrity",
            "model_configuration",
            "release_metadata",
            "schedule_publication",
        ):
            RELEASE_GATE.labels(gate=gate).set(0)
        SCHEDULE_HORIZON_READY.labels(horizon="next_week").set(0)
        issues: list[str] = []
        counts: dict[str, int] = {}
        bundle_version = None
        manifest_sha256 = None
        embedding_model = None
        embedding_dimension = None
        reference_date = None
        last_schedule_date = None
        schedule_coverage_rows: list[tuple[str, str, int]] = []
        schedule_week_rows: list[tuple[str, str, int, int]] = []
        manifest: dict[str, Any] = {}
        capacity_stats: dict[str, int] = {}

        try:
            snapshot = self.structured_repository.readiness_snapshot(
                embedding_model=self.settings.FPT_EMBEDDING_MODEL,
                embedding_dimension=self.settings.EMBEDDING_DIMENSIONS,
                default_capacity=self.settings.DEFAULT_DOCTOR_CAPACITY_PER_SESSION,
                now=datetime.now(UTC),
            )
            checks["structured_database"] = True
            counts = dict(snapshot.counts)
            meta = snapshot.meta
            bundle_version = meta.get("bundle_version")
            embedding_model = meta.get("embedding_model")
            raw_dimension = meta.get("embedding_dimension")
            embedding_dimension = int(raw_dimension) if raw_dimension else None
            manifest = json.loads(meta.get("manifest_json", "{}"))
            overlay_enabled = meta.get("hackathon_approval_overlay") == "true"
            checks["approval_lane"] = (
                not overlay_enabled
                if self.settings.ENVIRONMENT.lower() == "production"
                else overlay_enabled
            )
            checks["emergency_template"] = snapshot.emergency_template_active
            schedule_coverage_rows = snapshot.schedule_coverage_rows
            schedule_week_rows = snapshot.schedule_week_rows
            capacity_stats = snapshot.capacity_stats
            for session_id, capacity_limit, occupied_count in (
                snapshot.booking_capacity_rows
            ):
                BOOKING_CAPACITY_LIMIT.labels(session_id=session_id).set(
                    capacity_limit
                )
                BOOKING_OCCUPIED.labels(session_id=session_id).set(occupied_count)

            stored_integrity = json.loads(meta.get("integrity_json", "{}"))
            manifest_sha256 = stored_integrity.get("manifest_sha256")
            seed_manifest_sha256 = meta.get("postgres_seed_manifest_sha256")
            seed_archive_sha256 = meta.get("postgres_seed_archive_sha256")
            checks["manifest_integrity"] = bool(
                stored_integrity.get("exact_file_set") is True
                and _valid_sha256(manifest_sha256)
                and seed_manifest_sha256 == manifest_sha256
                and _valid_sha256(seed_archive_sha256)
                and meta.get("postgres_seed_revision")
                == EXPECTED_DATABASE_REVISION
                and meta.get("runtime_database") == "postgresql"
                and manifest.get("bundle_version") == bundle_version
            )
            checks["required_data"] = _required_counts_match(manifest, counts)
            checks["release_metadata"] = _release_metadata_ready(
                manifest,
                self.settings,
            )
            checks["schedule_publication"] = _schedule_publication_ready(
                manifest,
                counts,
                schedule_week_rows,
            )
            checks["capacity_safety"] = _capacity_safety_ready(
                capacity_stats,
                self.settings,
            )
            checks["embedding_index"] = (
                counts.get("knowledge_chunks", 0) > 0
                and counts.get("embedded_knowledge_chunks")
                == counts.get("knowledge_chunks")
                and embedding_model == self.settings.FPT_EMBEDDING_MODEL
                and embedding_dimension == self.settings.EMBEDDING_DIMENSIONS
            )
            checks["booking_sessions"] = (
                counts.get("booking_sessions", 0) > 0
                if self.settings.BOOKING_PROVIDER == "local_prototype"
                else True
            )
            reference_date = snapshot.first_schedule_date.isoformat()
            last_schedule_date = snapshot.last_schedule_date.isoformat()
            _record_schedule_coverage(
                schedule_coverage_rows,
                reference_date=reference_date,
            )
        except Exception as exc:
            issues.append("STRUCTURED_POSTGRESQL_INVALID")
            logger.warning(
                "PostgreSQL structured readiness validation failed",
                extra={
                    "event": "structured_readiness_failed",
                    "error_type": exc.__class__.__name__,
                },
            )
        for gate in (
            "capacity_safety",
            "database_migration",
            "emergency_template",
            "manifest_integrity",
            "model_configuration",
            "release_metadata",
            "schedule_publication",
        ):
            RELEASE_GATE.labels(gate=gate).set(1 if checks[gate] else 0)

        for name, passed in checks.items():
            if not passed:
                issue = f"CHECK_FAILED_{name.upper()}"
                if issue not in issues:
                    issues.append(issue)
        ready = all(checks.values())
        return ReadinessResponse(
            status="ok" if ready else "error",
            app=self.settings.APP_NAME,
            version=self.settings.APP_VERSION,
            environment=self.settings.ENVIRONMENT,
            structured_bundle_ready=ready,
            structured_bundle_path="postgresql",
            counts=counts,
            checks=checks,
            issues=issues,
            bundle_version=bundle_version,
            manifest_sha256=manifest_sha256,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            reference_date=reference_date,
            last_schedule_date=last_schedule_date,
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
            logger.warning(
                "database health probe failed",
                extra={
                    "event": "database_health_probe_failed",
                    "error_type": exc.__class__.__name__,
                },
            )
            return DatabaseHealthResponse(
                status="error",
                database="postgresql",
                detail="Database connection check failed.",
            )
        return DatabaseHealthResponse(
            status="ok" if healthy else "error",
            database="postgresql",
            detail=None if healthy else "SELECT 1 did not return 1.",
        )


_REQUIRED_MANIFEST_COUNTS = {
    "service_prices": "historical_price_rows",
    "service_price_points": "nested_facility_prices",
    "bhyt_policies": "bhyt_policies",
    "schedule_documents": "schedule_documents",
    "schedule_entries": "schedule_entries",
    "knowledge_chunks": "seed_facts",
}


def _required_counts_match(
    manifest: dict[str, Any],
    actual_counts: dict[str, int],
) -> bool:
    """Compare runtime rows to the signed manifest instead of fixed snapshots."""

    expected_counts = manifest.get("counts")
    if not isinstance(expected_counts, dict):
        return False
    for runtime_key, manifest_key in _REQUIRED_MANIFEST_COUNTS.items():
        expected = expected_counts.get(manifest_key)
        if not isinstance(expected, int) or isinstance(expected, bool) or expected <= 0:
            return False
        if actual_counts.get(runtime_key) != expected:
            return False
    return True


def _release_metadata_ready(manifest: dict[str, Any], settings: Settings) -> bool:
    """Require the manifest's explicit release lane for this deployment mode."""

    if settings.ENVIRONMENT.lower() == "production":
        return manifest.get("ready_for_production") is True
    if settings.BOOKING_PROVIDER == "local_prototype":
        return manifest.get("ready_to_seed_local_prototype") is True
    return manifest.get("ready_to_seed_staging") is True


def _schedule_publication_ready(
    manifest: dict[str, Any],
    actual_counts: dict[str, int],
    actual_weeks: list[tuple[str, str, int, int]],
) -> bool:
    """Verify every discovered week is accepted, approved and fully imported."""

    manifest_counts = manifest.get("counts")
    manifest_weeks = manifest.get("schedule_week_summaries")
    if not isinstance(manifest_counts, dict) or not isinstance(manifest_weeks, list):
        return False

    expected_documents = manifest_counts.get("schedule_documents")
    expected_entries = manifest_counts.get("schedule_entries")
    if not isinstance(expected_documents, int) or not isinstance(expected_entries, int):
        return False
    if not (
        expected_documents > 0
        and expected_entries > 0
        and manifest_counts.get("schedule_documents_accepted")
        == expected_documents
        and manifest_counts.get("schedule_documents_review_required") == 0
        and actual_counts.get("schedule_documents") == expected_documents
        and actual_counts.get("schedule_documents_accepted") == expected_documents
        and actual_counts.get("schedule_documents_review_required") == 0
        and actual_counts.get("schedule_documents_runtime_eligible")
        == expected_documents
        and actual_counts.get("schedule_documents_approved") == expected_documents
        and actual_counts.get("schedule_entries") == expected_entries
    ):
        return False

    expected_by_week: dict[tuple[str, str], tuple[int, int]] = {}
    for item in manifest_weeks:
        if not isinstance(item, dict):
            return False
        start = item.get("week_start")
        end = item.get("week_end")
        documents = item.get("documents_validation_accepted")
        review_required = item.get("documents_review_required")
        entries = item.get("entries_published_to_review_dataset")
        if not (
            isinstance(start, str)
            and isinstance(end, str)
            and isinstance(documents, int)
            and documents > 0
            and review_required == 0
            and isinstance(entries, int)
            and entries > 0
        ):
            return False
        expected_by_week[(start, end)] = (documents, entries)

    actual_by_week = {
        (start, end): (documents, entries)
        for start, end, documents, entries in actual_weeks
    }
    return bool(expected_by_week) and actual_by_week == expected_by_week


def _capacity_safety_ready(
    stats: dict[str, int],
    settings: Settings,
) -> bool:
    """Keep the project threshold isolated from real hospital confirmation."""

    if settings.BOOKING_PROVIDER == "redirect_only":
        return True
    if settings.BOOKING_PROVIDER == "hospital":
        return bool(settings.HOSPITAL_API_BASE_URL)
    if settings.ENVIRONMENT.lower() == "production":
        return False
    if not settings.BOOKING_ALLOW_PROJECT_MVP_RULE:
        return False
    if settings.BOOKING_REQUIRE_APPROVED_CAPACITY_RULE:
        return stats.get("hospital_approved_rules", 0) > 0
    return (
        stats.get("rules", 0) > 0
        and stats.get("prototype_default_rules") == 1
        and stats.get("sessions", 0) > 0
        and stats.get("unsafe_sessions") == 0
        and stats.get("over_capacity_sessions") == 0
    )


def _model_configuration_ready(settings: Settings) -> bool:
    """Validate fixed model contracts without spending money on a live probe."""

    return bool(
        settings.API_KEY
        and settings.LLM_PROVIDER == "openai"
        and settings.EMBEDDING_PROVIDER == "openai"
        and settings.FPT_API_BASE_URL.startswith("https://")
        and settings.FPT_LLM_MODEL == "gpt-oss-120b"
        and settings.FPT_EMBEDDING_MODEL == "Vietnamese_Embedding"
        and settings.EMBEDDING_DIMENSIONS == 1024
    )


async def collect_runtime_readiness(
    settings: Settings,
    rate_limiter: Any,
    *,
    database_probe: Callable[[], tuple[bool, bool]] | None = None,
) -> dict[str, bool]:
    """Probe Redis/rate-limit storage and the migrated PostgreSQL database."""

    limiter_ready = True
    if settings.RATE_LIMIT_ENABLED:
        try:
            limiter_ready = bool(await rate_limiter.ping())
        except Exception as exc:
            limiter_ready = False
            logger.warning(
                "rate limit store readiness failed",
                extra={
                    "event": "rate_limit_store_readiness_failed",
                    "error_type": exc.__class__.__name__,
                },
            )
    DEPENDENCY_UP.labels(dependency="rate_limit_store").set(
        1 if limiter_ready else 0
    )

    active_database_probe = database_probe or _probe_postgres_release_state
    try:
        postgres_ready, migration_ready = await asyncio.to_thread(
            active_database_probe
        )
    except Exception as exc:
        postgres_ready = False
        migration_ready = False
        logger.warning(
            "postgres readiness failed",
            extra={
                "event": "postgres_readiness_failed",
                "error_type": exc.__class__.__name__,
            },
        )
    DEPENDENCY_UP.labels(dependency="postgresql").set(
        1 if postgres_ready else 0
    )
    RELEASE_GATE.labels(gate="database_migration").set(
        1 if migration_ready else 0
    )
    checks = {
        "rate_limit_store": limiter_ready,
        "postgresql": postgres_ready,
        "database_migration": migration_ready,
    }
    if settings.RATE_LIMIT_STORAGE == "redis":
        checks["redis"] = limiter_ready
    return checks


def _probe_postgres_release_state() -> tuple[bool, bool]:
    from app.core.database import SessionLocal

    with SessionLocal() as session:
        repository = DatabaseHealthRepository(session)
        try:
            connected = repository.ping()
        except Exception:
            return False, False
        if not connected:
            return False, False
        try:
            migration_ready = repository.migration_is_current()
        except Exception:
            migration_ready = False
        return True, migration_ready


def _valid_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdefABCDEF" for character in value)


def _record_schedule_coverage(
    rows: list[tuple[str, str, int]],
    *,
    reference_date: str,
) -> None:
    """Export bounded immutable schedule coverage and the simulated next week."""

    expected_by_facility: dict[str, int] = {}
    for _, facility, eligible_count in rows:
        expected_by_facility[facility] = max(
            expected_by_facility.get(facility, 0),
            eligible_count,
        )

    ratios: dict[tuple[str, str], float] = {}
    for week, facility, eligible_count in rows:
        expected = expected_by_facility.get(facility, 0)
        ratio = min(1.0, eligible_count / expected) if expected else 0.0
        ratios[(week, facility)] = ratio
        SCHEDULE_COVERAGE.labels(facility=facility, week=week).set(ratio)

    reference = date.fromisoformat(reference_date)
    current_monday = reference - timedelta(days=reference.weekday())
    next_week = (current_monday + timedelta(days=7)).isoformat()
    next_week_ready = bool(expected_by_facility) and all(
        ratios.get((next_week, facility), 0.0) >= 1.0
        for facility in expected_by_facility
    )
    SCHEDULE_HORIZON_READY.labels(horizon="next_week").set(
        1 if next_week_ready else 0
    )

