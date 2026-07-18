"""Focused PostgreSQL structured-read tests; no network/provider is used."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from app.services.structured import (
    _deduplicate_schedule_rows,
    _extract_room_query,
    _resolve_schedule_date,
)
from app.structured.postgres_repository import PostgresStructuredRepository


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._scalar


class FakeSession:
    def __init__(
        self,
        responder: Callable[[str, dict[str, Any]], FakeResult],
        calls: list[tuple[str, dict[str, Any]]],
    ):
        self._responder = responder
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, params=None):
        sql = str(statement)
        bound = dict(params or {})
        self._calls.append((sql, bound))
        return self._responder(sql, bound)


class FakeSessionFactory:
    def __init__(self, responder):
        self.responder = responder
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self):
        return FakeSession(self.responder, self.calls)


def test_price_search_binds_input_and_orders_exact_before_trigram() -> None:
    query = "dịch vụ"

    def responder(sql, params):
        assert "service_catalog_records" in sql
        return FakeResult(
            [
                {
                    "service_record_id": "SERVICE-1",
                    "display_name": "Dịch vụ",
                    "section": "A",
                    "ghi_chu": None,
                    "historical_year": 2026,
                    "source_id": "SOURCE-1",
                    "display_name_search": "dich vu",
                    "price_id": "PRICE-1",
                    "facility_code": "CS1",
                    "amount_vnd": 100_000,
                    "amount_raw": "100000",
                    "exact_match": False,
                    "search_contains": False,
                    "name_similarity": 0.75,
                }
            ]
        )

    factory = FakeSessionFactory(responder)
    repository = PostgresStructuredRepository(factory)

    rows = repository.search_service_prices(
        query=query,
        facility_code="CS1",
        limit=7,
    )

    sql, params = factory.calls[0]
    assert query not in sql
    assert params["query_pattern"].startswith("%")
    assert params["facility_code"] == "CS1"
    assert params["row_limit"] == 50
    assert "similarity(sp.display_name_folded" in sql
    assert "sp.display_name_search LIKE :query_pattern" in sql
    assert "ORDER BY exact_match DESC, search_contains DESC, name_similarity DESC" in sql
    assert rows[0]["price_id"] == "PRICE-1"


def test_pgvector_search_is_native_parameterized_and_intent_filtered() -> None:
    def responder(sql, params):
        return FakeResult(
            [
                {
                    "chunk_id": "CHUNK-1",
                    "fact_id": "FACT-1",
                    "source_id": "SOURCE-1",
                    "content_vi": "Kênh đặt lịch chính thức.",
                    "embedding_model": "Vietnamese_Embedding",
                    "embedding_dimension": 1024,
                    "allowed_intents_json": '["booking"]',
                    "title": "Nguồn chính thức",
                    "url": None,
                    "publisher": "Hospital",
                    "score": 0.91,
                }
            ]
        )

    factory = FakeSessionFactory(responder)
    repository = PostgresStructuredRepository(factory)
    vector = [0.001] * 1024

    rows = repository.search_embedded_knowledge_chunks(
        query_vector=vector,
        allowed_intents={"booking"},
        limit=3,
        minimum_score=0.6,
    )

    sql, params = factory.calls[0]
    assert "<=> CAST(:query_vector AS vector)" in sql
    assert "jsonb_array_elements_text" in sql
    assert "ORDER BY kc.embedding <=>" in sql
    assert params["query_vector"] == json.dumps(vector, separators=(",", ":"))
    assert params["allowed_intents"] == ["booking"]
    assert params["minimum_score"] == 0.6
    assert rows[0]["score"] == 0.91


def test_pgvector_search_rejects_wrong_dimension_before_database_access() -> None:
    factory = FakeSessionFactory(lambda sql, params: FakeResult())
    repository = PostgresStructuredRepository(factory)

    with pytest.raises(ValueError, match="1024"):
        repository.search_embedded_knowledge_chunks(query_vector=[1.0, 0.0])

    assert factory.calls == []


def test_schedule_lookup_uses_typed_dates_and_returns_api_compatible_iso_date() -> None:
    def responder(sql, params):
        return FakeResult(
            [
                {
                    "schedule_entry_id": "SCHEDULE-1",
                    "document_id": "DOCUMENT-1",
                    "source_id": "SOURCE-1",
                    "service_date": date(2026, 7, 20),
                    "week_start": date(2026, 7, 20),
                    "week_end": date(2026, 7, 26),
                    "facility_code": "CS1",
                }
            ]
        )

    factory = FakeSessionFactory(responder)
    repository = PostgresStructuredRepository(factory)
    target_week = date(2026, 7, 20)

    rows = repository.find_schedule_entries(
        week_start=target_week,
        service_date=target_week,
        doctor_query="Nguyễn Văn A",
    )

    sql, params = factory.calls[0]
    assert "se.duty_status = 'scheduled'" in sql
    assert params["week_start"] == target_week
    assert params["service_date"] == target_week
    assert params["doctor_pattern"].startswith("%")
    assert params["doctor_folded"]
    assert params["doctor_match_min_score"] == 0.6
    assert "schedule_entry_doctors" in sql
    assert "word_similarity" in sql
    assert rows[0]["service_date"] == "2026-07-20"
    assert rows[0]["week_end"] == "2026-07-26"


def test_schedule_date_parser_accepts_day_month_without_year() -> None:
    reference = date(2026, 6, 8)

    assert _resolve_schedule_date("Bác sĩ nào khám ngày 09/06 ở CS1?", reference) == date(2026, 6, 9)
    assert _resolve_schedule_date("Cho tôi lịch 15-06 cơ sở 2", reference) == date(2026, 6, 15)
    assert _resolve_schedule_date("Lịch ngày 15/06/2026 ở cơ sở 1", reference) == date(2026, 6, 15)


def test_schedule_date_parser_does_not_flip_day_month_order() -> None:
    reference = date(2026, 6, 8)

    assert _resolve_schedule_date("Ngày 06/08 có bác sĩ nào?", reference) == date(2026, 8, 6)
    assert _resolve_schedule_date("Ngày 08/06 có bác sĩ nào?", reference) == date(2026, 6, 8)


def test_schedule_date_parser_accepts_single_digit_month() -> None:
    reference = date(2026, 6, 8)

    assert _resolve_schedule_date("cac ca kham ngay 19/7", reference) == date(2026, 7, 19)


def test_schedule_rows_are_deduplicated_by_published_slot() -> None:
    row = {
        "schedule_entry_id": "SCHEDULE-1",
        "service_date": "2026-07-19",
        "facility_code": "CS1",
        "room_label": "Phong 1",
        "unit_label": "Kham benh",
        "assignee_text_raw": "Bac si A",
        "published_hours_raw": "7.30 - 16.30",
    }
    duplicate = {**row, "schedule_entry_id": "SCHEDULE-2"}

    assert _deduplicate_schedule_rows([row, duplicate]) == [row]


def test_schedule_room_parser_extracts_only_room_identifier() -> None:
    assert _extract_room_query(
        "Ngày 09/06, phòng PK NHI (P402) tại CS2 có bác sĩ nào?"
    ) == "P402"
    assert _extract_room_query("Lịch phòng Nội chung tại cơ sở 2") == "noi chung"


def test_fact_ranking_filters_disallowed_intents_after_jsonb_read() -> None:
    def responder(sql, params):
        return FakeResult(
            [
                {
                    "fact_id": "FACT-BOOKING",
                    "source_id": "SOURCE-1",
                    "claim_vi": "Đặt lịch qua hotline chính thức",
                    "allowed_intents_json": '["booking"]',
                    "title": "Nguồn",
                    "url": None,
                    "publisher": "Hospital",
                },
                {
                    "fact_id": "FACT-OTHER",
                    "source_id": "SOURCE-1",
                    "claim_vi": "Đặt lịch qua kênh khác",
                    "allowed_intents_json": '["unsupported"]',
                    "title": "Nguồn",
                    "url": None,
                    "publisher": "Hospital",
                },
            ]
        )

    repository = PostgresStructuredRepository(FakeSessionFactory(responder))
    rows = repository.search_facts(
        query="đặt lịch hotline",
        allowed_intents={"booking"},
    )

    assert [row["fact_id"] for row in rows] == ["FACT-BOOKING"]
    assert rows[0]["allowed_intents"] == ["booking"]
