"""Read-only PostgreSQL access for approved HERA structured data.

The application runtime uses this repository directly against the pooled
SQLAlchemy engine configured in :mod:`app.core.database`. Portable seed
archives are build artifacts only; runtime reads never fall back to a file
database.
"""

from __future__ import annotations

import json
import math
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

SessionFactory = Callable[[], Session]


_PGVECTOR_SEARCH_SQL = """
    SELECT
        kc.chunk_id,
        kc.fact_id,
        kc.source_id,
        kc.content_vi,
        kc.embedding_model,
        kc.embedding_dimension,
        f.allowed_intents_json::text AS allowed_intents_json,
        s.title,
        s.canonical_url AS url,
        s.publisher,
        1 - (kc.embedding <=> CAST(:query_vector AS vector)) AS score
    FROM knowledge_chunks kc
    JOIN official_facts f ON f.fact_id = kc.fact_id
    JOIN official_sources s ON s.source_id = kc.source_id
    WHERE kc.retrieval_eligible IS TRUE
      AND kc.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
      AND f.retrieval_eligible IS TRUE
      AND f.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
      AND s.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
      AND kc.embedding IS NOT NULL
      AND (
            :filter_intents IS FALSE
            OR EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(
                    f.allowed_intents_json
                ) AS intent(value)
                WHERE intent.value = ANY(CAST(:allowed_intents AS TEXT[]))
            )
          )
      AND 1 - (kc.embedding <=> CAST(:query_vector AS vector))
            >= :minimum_score
    ORDER BY kc.embedding <=> CAST(:query_vector AS vector), kc.chunk_id
    LIMIT :row_limit
"""


@dataclass(frozen=True)
class StructuredRepositoryStats:
    """Small availability summary used by application readiness checks."""

    service_prices: int
    bhyt_policies: int
    schedule_documents: int
    schedule_entries: int


@dataclass(frozen=True)
class StructuredReadinessSnapshot:
    """Consistent set of bounded PostgreSQL release/readiness facts."""

    counts: dict[str, int]
    meta: dict[str, str]
    emergency_template_active: bool
    schedule_coverage_rows: list[tuple[str, str, int]]
    schedule_week_rows: list[tuple[str, str, int, int]]
    capacity_stats: dict[str, int]
    booking_capacity_rows: list[tuple[str, int, int]]
    first_schedule_date: date
    last_schedule_date: date


class StructuredReadRepository(Protocol):
    """Read contract shared by structured services and the RAG retriever."""

    def exists(self) -> bool: ...

    def stats(self) -> StructuredRepositoryStats: ...

    def search_service_prices(
        self,
        *,
        query: str,
        facility_code: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]: ...

    def find_bhyt_policy(
        self,
        *,
        as_of: date,
        latest_available: bool = False,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]: ...

    def find_schedule_entries(
        self,
        *,
        week_start: date,
        service_date: date | None = None,
        facility_code: str | None = None,
        doctor_query: str | None = None,
        room_query: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...

    def reference_date(self) -> date: ...

    def schedule_date_range(self) -> tuple[date, date]: ...

    def get_active_template(self, template_key: str) -> str | None: ...

    def get_support_channels(self) -> list[dict[str, Any]]: ...

    def search_facts(
        self,
        *,
        query: str,
        allowed_intents: set[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]: ...

    def get_embedded_knowledge_chunks(self) -> list[dict[str, Any]]: ...

    def search_embedded_knowledge_chunks(
        self,
        *,
        query_vector: list[float],
        allowed_intents: set[str] | None = None,
        limit: int = 5,
        minimum_score: float = 0.55,
    ) -> list[dict[str, Any]]: ...

    def get_sources_by_ids(
        self,
        source_ids: list[str],
    ) -> dict[str, dict[str, Any]]: ...

    def get_bundle_meta(self, key: str) -> str | None: ...

    def readiness_snapshot(
        self,
        *,
        embedding_model: str,
        embedding_dimension: int,
        default_capacity: int,
        now: datetime,
    ) -> StructuredReadinessSnapshot: ...


class PostgresStructuredRepository:
    """Read approved structured/reference data from PostgreSQL only."""

    def __init__(
        self,
        session_factory: SessionFactory | None = None,
        *,
        approval_statuses: Sequence[str] = (
            "approved_for_hackathon",
            "approved_for_production",
        ),
    ) -> None:
        if session_factory is None:
            # Import lazily so pure unit tests can inject a fake session without
            # constructing the process-global database engine.
            from app.core.database import SessionLocal

            session_factory = SessionLocal
        statuses = tuple(dict.fromkeys(str(item) for item in approval_statuses))
        if not statuses:
            raise ValueError("At least one approval status is required")
        self._session_factory = session_factory
        self._approval_statuses = list(statuses)

    def exists(self) -> bool:
        """Return whether the migrated structured schema is reachable."""

        try:
            with self._session_factory() as session:
                return bool(
                    session.execute(
                        text("SELECT to_regclass(:table_name) IS NOT NULL"),
                        {"table_name": "bundle_meta"},
                    ).scalar_one()
                )
        except Exception:
            return False

    def stats(self) -> StructuredRepositoryStats:
        row = self._one(
            """
            SELECT
                (SELECT COUNT(*) FROM service_catalog_records) AS service_prices,
                (SELECT COUNT(*) FROM bhyt_household_policies) AS bhyt_policies,
                (SELECT COUNT(*) FROM schedule_documents) AS schedule_documents,
                (SELECT COUNT(*) FROM schedule_entries) AS schedule_entries
            """
        )
        if row is None:
            raise LookupError("PostgreSQL structured tables are unavailable")
        return StructuredRepositoryStats(
            service_prices=int(row["service_prices"]),
            bhyt_policies=int(row["bhyt_policies"]),
            schedule_documents=int(row["schedule_documents"]),
            schedule_entries=int(row["schedule_entries"]),
        )

    def search_service_prices(
        self,
        *,
        query: str,
        facility_code: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT
                sp.service_record_id,
                sp.display_name_raw AS display_name,
                sp.source_section AS section,
                sp.note_raw AS ghi_chu,
                sp.historical_year,
                sp.source_id,
                spp.price_id,
                spp.facility_code,
                spp.amount_vnd,
                spp.raw_value AS amount_raw,
                sp.display_name_folded = :query_folded AS exact_match,
                similarity(sp.display_name_folded, :query_folded)
                    AS name_similarity
            FROM service_catalog_records sp
            JOIN service_price_snapshots spp
              ON spp.service_record_id = sp.service_record_id
            WHERE (
                    sp.display_name_folded = :query_folded
                    OR sp.display_name_folded LIKE :query_pattern
                    OR similarity(sp.display_name_folded, :query_folded)
                       >= :minimum_similarity
                  )
              AND sp.historical_lookup_eligible IS TRUE
              AND spp.historical_lookup_eligible IS TRUE
              AND sp.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
              AND (
                    CAST(:facility_code AS TEXT) IS NULL
                    OR spp.facility_code = CAST(:facility_code AS TEXT)
                  )
            ORDER BY exact_match DESC, name_similarity DESC,
                     LENGTH(sp.display_name_search), sp.service_record_id,
                     spp.facility_code, spp.price_id
            LIMIT :row_limit
            """,
            {
                "query_pattern": f"%{_fold_text(query)}%",
                "query_folded": _fold_text(query),
                "minimum_similarity": 0.25,
                "facility_code": facility_code,
                "row_limit": _bounded_limit(limit, maximum=100),
                "approval_statuses": self._approval_statuses,
            },
        )

    def find_bhyt_policy(
        self,
        *,
        as_of: date,
        latest_available: bool = False,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        validity = "" if latest_available else """
            AND valid_from <= :as_of
            AND (valid_to IS NULL OR valid_to >= :as_of)
        """
        policy = self._one(
            f"""
            SELECT *
            FROM bhyt_household_policies
            WHERE approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
              {validity}
            ORDER BY current_lookup_eligible DESC, valid_from DESC, policy_id
            LIMIT 1
            """,
            {
                "approval_statuses": self._approval_statuses,
                "as_of": as_of,
            },
        )
        if policy is None:
            return None, []
        tiers = self._all(
            """
            SELECT tier_id AS tier_key, policy_id, tier_order,
                   tier_label AS member_label, rate_text,
                   monthly_amount_vnd, annual_amount_vnd
            FROM bhyt_contribution_tiers
            WHERE policy_id = :policy_id
            ORDER BY tier_order
            """,
            {"policy_id": policy["policy_id"]},
        )
        return policy, tiers

    def find_schedule_entries(
        self,
        *,
        week_start: date,
        service_date: date | None = None,
        facility_code: str | None = None,
        doctor_query: str | None = None,
        room_query: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = self._all(
            """
            SELECT
                se.*,
                sd.source_path,
                sd.source_sha256,
                sd.coverage_status
            FROM schedule_entries se
            JOIN schedule_documents sd ON sd.document_id = se.document_id
            WHERE se.week_start = :week_start
              AND sd.validation_status = 'accepted'
              AND sd.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
              AND sd.runtime_eligible IS TRUE
              AND se.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
              AND se.runtime_eligible IS TRUE
              AND (
                    CAST(:service_date AS DATE) IS NULL
                    OR se.service_date = CAST(:service_date AS DATE)
                  )
              AND (
                    CAST(:facility_code AS TEXT) IS NULL
                    OR se.facility_code = CAST(:facility_code AS TEXT)
                  )
              AND (
                    CAST(:doctor_pattern AS TEXT) IS NULL
                    OR se.assignee_text_folded LIKE CAST(:doctor_pattern AS TEXT)
                  )
              AND (
                    CAST(:room_pattern AS TEXT) IS NULL
                    OR se.room_label_folded LIKE CAST(:room_pattern AS TEXT)
                  )
            ORDER BY se.service_date, se.room_label, se.schedule_entry_id
            LIMIT :row_limit
            """,
            {
                "week_start": week_start,
                "service_date": service_date,
                "facility_code": facility_code,
                "doctor_pattern": (
                    f"%{_fold_text(doctor_query)}%" if doctor_query else None
                ),
                "room_pattern": f"%{_fold_text(room_query)}%" if room_query else None,
                "row_limit": _bounded_limit(limit, maximum=500),
                "approval_statuses": self._approval_statuses,
            },
        )

        for row in rows:
            for key in ("service_date", "week_start", "week_end"):
                if row.get(key) is not None:
                    row[key] = _as_date(row[key]).isoformat()
        return rows

    def reference_date(self) -> date:
        row = self._one(
            """
            SELECT MIN(service_date) AS reference_date
            FROM schedule_entries
            WHERE runtime_eligible IS TRUE
              AND approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
            """,
            {"approval_statuses": self._approval_statuses},
        )
        if row is None or row["reference_date"] is None:
            raise LookupError("No approved schedule date is available")
        return _as_date(row["reference_date"])

    def schedule_date_range(self) -> tuple[date, date]:
        row = self._one(
            """
            SELECT MIN(service_date) AS first_date,
                   MAX(service_date) AS last_date
            FROM schedule_entries
            WHERE runtime_eligible IS TRUE
              AND approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
            """,
            {"approval_statuses": self._approval_statuses},
        )
        if row is None or row["first_date"] is None or row["last_date"] is None:
            raise LookupError("No approved schedule date range is available")
        return _as_date(row["first_date"]), _as_date(row["last_date"])

    def get_active_template(self, template_key: str) -> str | None:
        row = self._one(
            """
            SELECT text_vi
            FROM fixed_response_templates
            WHERE template_key = :template_key
              AND is_active IS TRUE
              AND approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
            ORDER BY version DESC
            LIMIT 1
            """,
            {
                "template_key": template_key,
                "approval_statuses": self._approval_statuses,
            },
        )
        return str(row["text_vi"]) if row else None

    def get_support_channels(self) -> list[dict[str, Any]]:
        return self._all(
            """
            SELECT channel_id, channel_type, label_vi, target_value,
                   source_fact_id
            FROM support_channels
            WHERE is_active IS TRUE
            ORDER BY channel_id
            """
        )

    def search_facts(
        self,
        *,
        query: str,
        allowed_intents: set[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Deterministically rank the bounded approved fact set in memory."""

        rows = self._all(
            """
            SELECT f.fact_id, f.source_id, f.claim_vi,
                   f.allowed_intents_json::text AS allowed_intents_json,
                   f.verified_at, f.valid_from, f.valid_to, f.usage_note,
                   s.title, s.canonical_url AS url, s.publisher
            FROM official_facts f
            JOIN official_sources s ON s.source_id = f.source_id
            WHERE f.retrieval_eligible IS TRUE
              AND f.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
              AND s.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
            """,
            {"approval_statuses": self._approval_statuses},
        )
        query_tokens = _search_tokens(query)
        ranked: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            intents = set(_json_array(row.get("allowed_intents_json")))
            if allowed_intents and not intents.intersection(allowed_intents):
                continue
            score = len(query_tokens.intersection(_search_tokens(row["claim_vi"])))
            if score == 0 and query_tokens:
                continue
            payload = dict(row)
            payload["allowed_intents"] = sorted(intents)
            payload["score"] = score
            ranked.append((score, payload))
        ranked.sort(key=lambda item: (-item[0], item[1]["fact_id"]))
        return [payload for _, payload in ranked[: _bounded_limit(limit, maximum=100)]]

    def get_embedded_knowledge_chunks(self) -> list[dict[str, Any]]:
        """Return approved vectors in the legacy JSON-compatible read shape."""

        return self._all(
            """
            SELECT
                kc.chunk_id,
                kc.fact_id,
                kc.source_id,
                kc.content_vi,
                kc.embedding::text AS embedding_json,
                kc.embedding_model,
                kc.embedding_dimension,
                f.allowed_intents_json::text AS allowed_intents_json,
                s.title,
                s.canonical_url AS url,
                s.publisher
            FROM knowledge_chunks kc
            JOIN official_facts f ON f.fact_id = kc.fact_id
            JOIN official_sources s ON s.source_id = kc.source_id
            WHERE kc.retrieval_eligible IS TRUE
              AND kc.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
              AND f.retrieval_eligible IS TRUE
              AND f.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
              AND s.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
              AND kc.embedding IS NOT NULL
            ORDER BY kc.chunk_id
            """,
            {"approval_statuses": self._approval_statuses},
        )

    def search_embedded_knowledge_chunks(
        self,
        query_vector: list[float],
        allowed_intents: set[str] | None = None,
        limit: int = 5,
        minimum_score: float = 0.55,
    ) -> list[dict[str, Any]]:
        """Search approved chunks natively with pgvector cosine/HNSW."""

        if len(query_vector) != 1024 or not all(
            isinstance(value, int | float) and math.isfinite(float(value))
            for value in query_vector
        ):
            raise ValueError(
                "query_vector must contain 1024 finite numeric values"
            )
        if not -1.0 <= float(minimum_score) <= 1.0:
            raise ValueError("minimum_score must be between -1 and 1")
        intent_values = sorted(allowed_intents or set())
        return self._all(
            _PGVECTOR_SEARCH_SQL,
            {
                "query_vector": json.dumps(
                    [float(value) for value in query_vector],
                    separators=(",", ":"),
                ),
                "approval_statuses": self._approval_statuses,
                "filter_intents": bool(intent_values),
                "allowed_intents": intent_values,
                "minimum_score": float(minimum_score),
                "row_limit": _bounded_limit(limit, maximum=100),
            },
        )

    def get_sources_by_ids(
        self,
        source_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        unique_ids = list(dict.fromkeys(source_ids))
        if not unique_ids:
            return {}
        rows = self._all(
            """
            SELECT source_id, title, canonical_url AS url, authority,
                   publisher, published_at, retrieved_at, valid_from,
                   valid_to, approval_status, notes
            FROM official_sources
            WHERE source_id = ANY(CAST(:source_ids AS TEXT[]))
            """,
            {"source_ids": unique_ids},
        )
        return {str(row["source_id"]): row for row in rows}

    def get_bundle_meta(self, key: str) -> str | None:
        row = self._one(
            "SELECT value FROM bundle_meta WHERE key = :key",
            {"key": key},
        )
        return str(row["value"]) if row else None

    def readiness_snapshot(
        self,
        *,
        embedding_model: str,
        embedding_dimension: int,
        default_capacity: int,
        now: datetime,
    ) -> StructuredReadinessSnapshot:
        """Read every structured release gate through one pooled DB session."""

        with self._session_factory() as session:
            count_row = _mapping_one(
                session,
                """
                SELECT
                  (SELECT COUNT(*) FROM service_catalog_records) AS service_prices,
                  (SELECT COUNT(*) FROM service_price_snapshots) AS service_price_points,
                  (SELECT COUNT(*) FROM bhyt_household_policies) AS bhyt_policies,
                  (SELECT COUNT(*) FROM bhyt_contribution_tiers) AS bhyt_tiers,
                  (SELECT COUNT(*) FROM schedule_documents) AS schedule_documents,
                  (SELECT COUNT(*) FROM schedule_entries) AS schedule_entries,
                  (SELECT COUNT(*) FROM knowledge_chunks) AS knowledge_chunks,
                  (SELECT COUNT(*) FROM booking_sessions) AS booking_sessions,
                  (
                    SELECT COUNT(*) FROM knowledge_chunks
                    WHERE retrieval_eligible IS TRUE
                      AND embedding IS NOT NULL
                      AND embedding_model = :embedding_model
                      AND embedding_dimension = :embedding_dimension
                  ) AS embedded_knowledge_chunks
                """,
                {
                    "embedding_model": embedding_model,
                    "embedding_dimension": embedding_dimension,
                },
            )
            if count_row is None:
                raise LookupError("PostgreSQL structured release data is unavailable")
            counts = {key: int(value or 0) for key, value in count_row.items()}

            meta_rows = _mapping_all(session, "SELECT key, value FROM bundle_meta", {})
            meta = {str(row["key"]): str(row["value"]) for row in meta_rows}
            emergency_active = bool(
                session.execute(
                    text(
                        """
                        SELECT EXISTS(
                          SELECT 1 FROM fixed_response_templates
                          WHERE template_key = 'emergency'
                            AND is_active IS TRUE
                            AND approval_status = ANY(
                                CAST(:approval_statuses AS TEXT[])
                            )
                            AND LENGTH(TRIM(text_vi)) > 0
                        )
                        """
                    ),
                    {"approval_statuses": self._approval_statuses},
                ).scalar_one()
            )

            document_stats = _mapping_one(
                session,
                """
                SELECT
                  COUNT(*) FILTER (WHERE validation_status = 'accepted') AS accepted,
                  COUNT(*) FILTER (
                    WHERE validation_status = 'review_required'
                  ) AS review_required,
                  COUNT(*) FILTER (WHERE runtime_eligible IS TRUE) AS runtime_eligible,
                  COUNT(*) FILTER (
                    WHERE approval_status NOT IN ('pending', 'rejected')
                  ) AS approved
                FROM schedule_documents
                """,
                {},
            ) or {}
            counts.update(
                {
                    "schedule_documents_accepted": int(document_stats.get("accepted") or 0),
                    "schedule_documents_review_required": int(
                        document_stats.get("review_required") or 0
                    ),
                    "schedule_documents_runtime_eligible": int(
                        document_stats.get("runtime_eligible") or 0
                    ),
                    "schedule_documents_approved": int(
                        document_stats.get("approved") or 0
                    ),
                }
            )

            coverage = _mapping_all(
                session,
                """
                SELECT folder_week_start, facility_code,
                       COUNT(*) FILTER (WHERE runtime_eligible IS TRUE) AS eligible
                FROM schedule_documents
                WHERE folder_week_start IS NOT NULL AND facility_code IS NOT NULL
                GROUP BY folder_week_start, facility_code
                ORDER BY folder_week_start, facility_code
                """,
                {},
            )
            schedule_coverage_rows = [
                (
                    _as_date(row["folder_week_start"]).isoformat(),
                    str(row["facility_code"]),
                    int(row["eligible"] or 0),
                )
                for row in coverage
            ]

            weeks = _mapping_all(
                session,
                """
                SELECT d.folder_week_start, d.folder_week_end,
                       COUNT(DISTINCT d.document_id) AS documents,
                       COUNT(e.schedule_entry_id) AS entries
                FROM schedule_documents d
                LEFT JOIN schedule_entries e ON e.document_id = d.document_id
                GROUP BY d.folder_week_start, d.folder_week_end
                ORDER BY d.folder_week_start
                """,
                {},
            )
            schedule_week_rows = [
                (
                    _as_date(row["folder_week_start"]).isoformat(),
                    _as_date(row["folder_week_end"]).isoformat(),
                    int(row["documents"] or 0),
                    int(row["entries"] or 0),
                )
                for row in weeks
            ]

            capacity_rule_stats = _mapping_one(
                session,
                """
                SELECT COUNT(*) AS rules,
                       COUNT(*) FILTER (
                         WHERE capacity_rule_id =
                               'CAPACITY-DEFAULT-PER-DOCTOR-SESSION'
                           AND max_patients = :default_capacity
                           AND config_source = 'project_mvp_default'
                           AND hospital_approved IS FALSE
                           AND production_eligible IS FALSE
                       ) AS prototype_default_rules,
                       COUNT(*) FILTER (
                         WHERE hospital_approved IS TRUE
                       ) AS hospital_approved_rules
                FROM booking_capacity_rules
                """,
                {"default_capacity": default_capacity},
            ) or {}
            session_stats = _mapping_one(
                session,
                """
                SELECT COUNT(*) AS sessions,
                       COUNT(*) FILTER (
                         WHERE capacity_limit != :default_capacity
                            OR prototype_only IS NOT TRUE
                            OR status != 'open'
                       ) AS unsafe_sessions
                FROM booking_sessions
                """,
                {"default_capacity": default_capacity},
            ) or {}
            capacity_rows = _mapping_all(
                session,
                """
                SELECT bs.booking_session_id, bs.capacity_limit,
                       COUNT(bh.hold_id) FILTER (
                         WHERE bh.status = 'confirmed'
                            OR (bh.status = 'held' AND bh.expires_at > :now)
                       ) AS occupied_count
                FROM booking_sessions bs
                LEFT JOIN booking_holds bh
                  ON bh.booking_session_id = bs.booking_session_id
                WHERE bs.status = 'open'
                GROUP BY bs.booking_session_id, bs.capacity_limit
                ORDER BY bs.booking_session_id
                """,
                {"now": now},
            )
            booking_capacity_rows = [
                (
                    str(row["booking_session_id"]),
                    int(row["capacity_limit"]),
                    int(row["occupied_count"] or 0),
                )
                for row in capacity_rows
            ]
            capacity_stats = {
                "rules": int(capacity_rule_stats.get("rules") or 0),
                "prototype_default_rules": int(
                    capacity_rule_stats.get("prototype_default_rules") or 0
                ),
                "hospital_approved_rules": int(
                    capacity_rule_stats.get("hospital_approved_rules") or 0
                ),
                "sessions": int(session_stats.get("sessions") or 0),
                "unsafe_sessions": int(session_stats.get("unsafe_sessions") or 0),
                "over_capacity_sessions": sum(
                    occupied > capacity
                    for _, capacity, occupied in booking_capacity_rows
                ),
            }
            counts["booking_capacity_rules"] = capacity_stats["rules"]
            counts["booking_unsafe_sessions"] = capacity_stats["unsafe_sessions"]
            counts["booking_over_capacity_sessions"] = capacity_stats[
                "over_capacity_sessions"
            ]

            range_row = _mapping_one(
                session,
                """
                SELECT MIN(service_date) AS first_date,
                       MAX(service_date) AS last_date
                FROM schedule_entries
                WHERE runtime_eligible IS TRUE
                  AND approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
                """,
                {"approval_statuses": self._approval_statuses},
            )
            if (
                range_row is None
                or range_row["first_date"] is None
                or range_row["last_date"] is None
            ):
                raise LookupError("No approved schedule date range is available")

        return StructuredReadinessSnapshot(
            counts=counts,
            meta=meta,
            emergency_template_active=emergency_active,
            schedule_coverage_rows=schedule_coverage_rows,
            schedule_week_rows=schedule_week_rows,
            capacity_stats=capacity_stats,
            booking_capacity_rows=booking_capacity_rows,
            first_schedule_date=_as_date(range_row["first_date"]),
            last_schedule_date=_as_date(range_row["last_date"]),
        )

    def _all(
        self,
        statement: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            return _mapping_all(session, statement, params or {})

    def _one(
        self,
        statement: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._session_factory() as session:
            return _mapping_one(session, statement, params or {})


def _mapping_all(
    session: Session,
    statement: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    result = session.execute(text(statement), params)
    return [dict(row) for row in result.mappings().all()]


def _mapping_one(
    session: Session,
    statement: str,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    row = session.execute(text(statement), params).mappings().first()
    return dict(row) if row is not None else None


def _bounded_limit(value: int, *, maximum: int) -> int:
    if isinstance(value, bool) or value < 1:
        raise ValueError("limit must be a positive integer")
    return min(int(value), maximum)


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _json_array(value: Any) -> list[str]:
    if value is None:
        return []
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, list):
        raise ValueError("Expected a JSON array")
    return [str(item) for item in payload]


def _fold_text(value: str | None) -> str:
    text_value = (value or "").strip().lower()
    decomposed = unicodedata.normalize("NFD", text_value)
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return without_marks.replace("đ", "d")


def _search_tokens(value: str) -> set[str]:
    return {
        token
        for token in _fold_text(value).replace("/", " ").replace("-", " ").split()
        if len(token) > 1
    }
