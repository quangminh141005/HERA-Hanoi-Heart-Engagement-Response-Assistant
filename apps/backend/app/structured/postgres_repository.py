"""Read-only PostgreSQL access for approved HERA structured data.

The application runtime uses this repository directly against the pooled
SQLAlchemy engine configured in :mod:`app.core.database`. Portable seed
archives are build artifacts only; runtime reads never fall back to a file
database.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
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
        doctor_match_min_score: float = 0.60,
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
        self._doctor_match_min_score = min(
            1.0,
            max(0.0, float(doctor_match_min_score)),
        )

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
        query_folded = _fold_text(query)
        query_terms = _service_price_query_tokens(query_folded)
        rows = self._all(
            """
            SELECT
                sp.service_record_id,
                sp.display_name_raw AS display_name,
                sp.source_section AS section,
                sp.note_raw AS ghi_chu,
                sp.historical_year,
                sp.source_id,
                sp.display_name_search,
                spp.price_id,
                spp.facility_code,
                spp.amount_vnd,
                spp.raw_value AS amount_raw,
                sp.display_name_folded = :query_folded AS exact_match,
                sp.display_name_search LIKE :query_pattern AS search_contains,
                GREATEST(
                    similarity(sp.display_name_folded, :query_folded),
                    similarity(sp.display_name_search, :query_folded)
                ) AS name_similarity
            FROM service_catalog_records sp
            JOIN service_price_snapshots spp
              ON spp.service_record_id = sp.service_record_id
            WHERE (
                    sp.display_name_folded = :query_folded
                    OR sp.display_name_folded LIKE :query_pattern
                    OR sp.display_name_search LIKE :query_pattern
                    OR similarity(sp.display_name_folded, :query_folded)
                       >= :minimum_similarity
                    OR similarity(sp.display_name_search, :query_folded)
                       >= :minimum_similarity
                    OR (
                        cardinality(CAST(:query_terms AS TEXT[])) > 0
                        AND NOT EXISTS (
                            SELECT 1
                            FROM unnest(CAST(:query_terms AS TEXT[])) AS term(value)
                            WHERE sp.display_name_search NOT LIKE '%' || term.value || '%'
                        )
                    )
                  )
              AND sp.historical_lookup_eligible IS TRUE
              AND spp.historical_lookup_eligible IS TRUE
              AND sp.approval_status = ANY(CAST(:approval_statuses AS TEXT[]))
              AND (
                    CAST(:facility_code AS TEXT) IS NULL
                    OR spp.facility_code = CAST(:facility_code AS TEXT)
                  )
            ORDER BY exact_match DESC, search_contains DESC, name_similarity DESC,
                     LENGTH(sp.display_name_search), sp.service_record_id,
                     spp.facility_code, spp.price_id
            LIMIT :row_limit
            """,
            {
                "query_pattern": f"%{query_folded}%",
                "query_folded": query_folded,
                "query_terms": query_terms,
                "minimum_similarity": 0.25,
                "facility_code": facility_code,
                "row_limit": max(_bounded_limit(limit, maximum=100), 50),
                "approval_statuses": self._approval_statuses,
            },
        )
        return _rerank_service_price_rows(query, rows, limit=limit)

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
              AND se.duty_status = 'scheduled'
              AND (
                    CAST(:service_date AS DATE) IS NULL
                    OR se.service_date = CAST(:service_date AS DATE)
                  )
              AND (
                    CAST(:facility_code AS TEXT) IS NULL
                    OR se.facility_code = CAST(:facility_code AS TEXT)
                  )
              AND (
                    CAST(:doctor_folded AS TEXT) IS NULL
                    OR se.assignee_text_folded LIKE CAST(:doctor_pattern AS TEXT)
                    OR word_similarity(
                        se.assignee_text_folded,
                        CAST(:doctor_folded AS TEXT)
                    ) >= :doctor_match_min_score
                    OR EXISTS (
                        SELECT 1
                        FROM schedule_entry_doctors sed
                        JOIN doctors d ON d.doctor_id = sed.doctor_id
                        WHERE sed.entry_id = se.schedule_entry_id
                          AND (
                            CAST(:doctor_folded AS TEXT)
                              LIKE '%' || d.normalized_name || '%'
                            OR d.normalized_name
                              LIKE '%' || CAST(:doctor_folded AS TEXT) || '%'
                            OR word_similarity(
                                d.normalized_name,
                                CAST(:doctor_folded AS TEXT)
                              ) >= :doctor_match_min_score
                          )
                    )
                  )
              AND (
                    CAST(:room_pattern AS TEXT) IS NULL
                    OR se.room_label_folded LIKE CAST(:room_pattern AS TEXT)
                  )
            ORDER BY
              CASE
                WHEN CAST(:doctor_folded AS TEXT) IS NULL THEN 0
                WHEN se.assignee_text_folded LIKE CAST(:doctor_pattern AS TEXT) THEN 2
                ELSE 1
              END DESC,
              se.service_date, se.room_label, se.schedule_entry_id
            LIMIT :row_limit
            """,
            {
                "week_start": week_start,
                "service_date": service_date,
                "facility_code": facility_code,
                "doctor_folded": _fold_text(doctor_query) if doctor_query else None,
                "doctor_pattern": f"%{_fold_text(doctor_query)}%" if doctor_query else None,
                "doctor_match_min_score": self._doctor_match_min_score,
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


def _rerank_service_price_rows(
    query: str,
    rows: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Prefer rows that cover meaningful query tokens before trigram similarity."""

    if not rows:
        return []
    query_folded = _fold_text(query)
    query_tokens = _service_price_query_tokens(query_folded)
    if not query_tokens:
        return rows[: _bounded_limit(limit, maximum=100)]
    query_bigrams = _token_ngrams(query_tokens, size=2)
    query_trigrams = _token_ngrams(query_tokens, size=3)
    query_weight = sum(_service_price_token_weight(token) for token in query_tokens)
    row_tokens: list[list[str]] = []
    haystacks: list[str] = []
    for row in rows:
        haystack = _fold_text(
            " ".join(
                str(row.get(key) or "")
                for key in ("display_name", "display_name_search", "section", "ghi_chu")
            )
        )
        haystacks.append(haystack)
        row_tokens.append(_service_price_query_tokens(haystack))
    bm25_scores = _bm25_scores(query_tokens, row_tokens)
    scored: list[tuple[float, dict[str, Any]]] = []
    for index, row in enumerate(rows):
        haystack = haystacks[index]
        primary_haystack = _fold_text(
            " ".join(
                str(row.get(key) or "")
                for key in ("display_name", "display_name_search")
            )
        )
        haystack_tokens = set(row_tokens[index])
        primary_tokens = set(_service_price_query_tokens(primary_haystack))
        weighted_hits = sum(
            _service_price_token_weight(token)
            for token in query_tokens
            if token in haystack_tokens
        )
        primary_weighted_hits = sum(
            _service_price_token_weight(token)
            for token in query_tokens
            if token in primary_tokens
        )
        coverage = weighted_hits / max(0.01, query_weight)
        primary_coverage = primary_weighted_hits / max(0.01, query_weight)
        bigram_hits = sum(1 for ngram in query_bigrams if ngram in haystack)
        trigram_hits = sum(1 for ngram in query_trigrams if ngram in haystack)
        bigram_score = bigram_hits / max(1, len(query_bigrams))
        trigram_score = trigram_hits / max(1, len(query_trigrams))
        phrase_bonus = 1.0 if query_folded and query_folded in haystack else 0.0
        exact_bonus = 1.0 if row.get("exact_match") else 0.0
        similarity = float(row.get("name_similarity") or 0.0)
        bm25_score = bm25_scores[index]
        score = (
            phrase_bonus * 5.0
            + bm25_score * 3.0
            + trigram_score * 3.0
            + bigram_score * 2.0
            + coverage * 2.0
            + exact_bonus * 2.0
            + similarity * 0.5
        )
        enriched = dict(row)
        enriched["_token_coverage"] = coverage
        enriched["_primary_token_coverage"] = primary_coverage
        enriched["_bigram_score"] = bigram_score
        enriched["_trigram_score"] = trigram_score
        enriched["_bm25_score"] = bm25_score
        enriched["_ranking_score"] = score
        scored.append((score, enriched))
    best_score = max(score for score, _ in scored)
    best_coverage = max(row["_token_coverage"] for _, row in scored)
    best_primary_coverage = max(row["_primary_token_coverage"] for _, row in scored)
    minimum_primary_coverage = _minimum_primary_coverage(query_tokens)
    if (
        best_coverage < 0.7
        or best_primary_coverage < minimum_primary_coverage
        or best_score < 2.1
    ):
        return []
    filtered = [
        item
        for item in scored
        if item[0] >= max(2.1, best_score - 2.0)
        and item[1]["_token_coverage"] >= max(0.65, best_coverage - 0.18)
        and item[1]["_primary_token_coverage"]
        >= max(minimum_primary_coverage - 0.05, best_primary_coverage - 0.2)
    ]
    filtered.sort(
        key=lambda item: (
            -item[0],
            -float(item[1].get("name_similarity") or 0.0),
            len(str(item[1].get("display_name") or "")),
            str(item[1].get("service_record_id") or ""),
            str(item[1].get("facility_code") or ""),
        )
    )
    clean_rows: list[dict[str, Any]] = []
    for _, row in filtered[: _bounded_limit(limit, maximum=100)]:
        row.pop("_token_coverage", None)
        row.pop("_primary_token_coverage", None)
        row.pop("_bigram_score", None)
        row.pop("_trigram_score", None)
        row.pop("_bm25_score", None)
        row.pop("_ranking_score", None)
        clean_rows.append(row)
    return clean_rows


def _bm25_scores(
    query_tokens: list[str],
    document_tokens: list[list[str]],
    *,
    k1: float = 1.2,
    b: float = 0.75,
) -> list[float]:
    """Return normalized Okapi BM25 scores for a small candidate set."""

    if not query_tokens or not document_tokens:
        return [0.0 for _ in document_tokens]
    doc_count = len(document_tokens)
    avgdl = sum(len(tokens) for tokens in document_tokens) / max(1, doc_count)
    frequencies = [Counter(tokens) for tokens in document_tokens]
    document_frequency: Counter[str] = Counter()
    for frequencies_for_doc in frequencies:
        for token in set(frequencies_for_doc):
            document_frequency[token] += 1

    scores: list[float] = []
    for tokens, frequencies_for_doc in zip(document_tokens, frequencies, strict=True):
        doc_len = max(1, len(tokens))
        raw_score = 0.0
        for token in query_tokens:
            term_frequency = frequencies_for_doc.get(token, 0)
            if term_frequency <= 0:
                continue
            idf = math.log(
                1.0
                + (doc_count - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            denominator = term_frequency + k1 * (1.0 - b + b * doc_len / max(1.0, avgdl))
            raw_score += idf * (term_frequency * (k1 + 1.0)) / denominator
        scores.append(raw_score)
    best_score = max(scores, default=0.0)
    if best_score <= 0:
        return [0.0 for _ in scores]
    return [score / best_score for score in scores]


def _minimum_primary_coverage(query_tokens: list[str]) -> float:
    """Require near-exact name coverage for short queries to avoid false positives."""

    unique_terms = set(query_tokens)
    if len(unique_terms) <= 3:
        return 0.95
    if len(unique_terms) <= 5:
        return 0.75
    return 0.65


def _token_ngrams(tokens: list[str], *, size: int) -> list[str]:
    if size < 2 or len(tokens) < size:
        return []
    return [" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)]


def _service_price_token_weight(token: str) -> float:
    """Downweight generic table words and preserve discriminative user terms.

    This is not intent hardcoding. It is a generic lexical ranking rule: common
    service-table words should not beat phrase continuity like "noi khoa" or
    exact discriminators such as numeric type labels.
    """

    if token.isdigit():
        return 1.4
    if len(token) <= 2:
        return 1.25
    if len(token) <= 4:
        return 1.0
    return 0.75


def _service_price_query_tokens(value: str) -> list[str]:
    """Tokenize the model-extracted service phrase without language word lists."""

    tokens = re.split(r"[^0-9a-zA-Z]+", value)
    return [
        token
        for token in tokens
        if len(token) > 1 or token.isdigit()
    ]


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
