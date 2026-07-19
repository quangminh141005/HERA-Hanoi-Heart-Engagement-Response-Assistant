'''Real PostgreSQL integration tests for structured endpoints and readiness.'''

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime

import httpx
import pytest
from app.core.config import Settings
from app.main import app
from app.routers.structured import get_structured_service
from app.services.health import HealthService
from app.services.structured import StructuredDataService
from app.structured.cache import NoopStructuredQueryCache
from app.structured.postgres_repository import PostgresStructuredRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration


@pytest.fixture(scope='module')
def pg_session_factory() -> Iterator[sessionmaker[Session]]:
    database_url = os.getenv('HERA_TEST_DATABASE_URL')
    if not database_url:
        pytest.skip('HERA_TEST_DATABASE_URL is not configured')
    engine = create_engine(database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repository = PostgresStructuredRepository(factory)
    if not repository.exists() or repository.stats().service_prices != 2_946:
        engine.dispose()
        pytest.fail('PostgreSQL test database must be migrated and seeded')
    yield factory
    engine.dispose()


@pytest.fixture
def structured_service(
    pg_session_factory: sessionmaker[Session],
) -> Iterator[StructuredDataService]:
    settings = Settings(
        RATE_LIMIT_ENABLED=False,
        API_KEY='offline-test-key',
        LLM_PROVIDER='openai',
        EMBEDDING_PROVIDER='openai',
        _env_file=None,
    )
    service = StructuredDataService(
        settings,
        repository=PostgresStructuredRepository(pg_session_factory),
        cache=NoopStructuredQueryCache(),
    )
    app.dependency_overrides[get_structured_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_structured_service, None)


async def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url='http://testserver',
    ) as client:
        return await client.get(path, headers={'X-Request-ID': 'postgres-test'})


def test_postgres_readiness_snapshot_passes_every_release_gate(
    structured_service: StructuredDataService,
) -> None:
    health = HealthService(
        settings=structured_service.settings,
        structured_repository=structured_service.repository,
    ).readiness_health(
        {
            'rate_limit_store': True,
            'postgresql': True,
            'database_migration': True,
        }
    )

    assert health.status == 'ok'
    assert health.issues == []
    assert all(health.checks.values())
    assert health.counts['service_prices'] == 2_946
    assert health.counts['schedule_entries'] == 1_558
    assert health.structured_bundle_path == 'postgresql'


def test_service_prices_endpoint_returns_project_latest_rows(
    structured_service: StructuredDataService,
) -> None:
    response = asyncio.run(
        _get('/api/v1/service-prices?query=kham&facility_code=CS1')
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['classification'] == 'official_current'
    assert payload['records']
    assert payload['records'][0]['facility_code'] == 'CS1'
    assert all('historical_year' not in row for row in payload['records'])
    assert payload['citations']


def test_bhyt_endpoint_uses_latest_seeded_policy(
    structured_service: StructuredDataService,
) -> None:
    response = asyncio.run(
        _get('/api/v1/bhyt/household-contributions?as_of=2026-07-17')
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['classification'] == 'official_current'
    assert len(payload['tiers']) == 5
    assert payload['tiers'][0]['annual_amount_vnd'] == 1_366_200
    assert 'quyền lợi cá nhân' in payload['warning']


def test_price_chat_combines_equal_facilities_without_showing_year(
    structured_service: StructuredDataService,
) -> None:
    result = structured_service.chat_service_price('Giá khám bệnh là bao nhiêu?')

    assert 'CS1 và CS2' in result.response
    assert '50.600 VND' in result.response
    assert '2025' not in result.response
    assert 'hệ thống,' in result.response


def test_price_chat_respects_explicit_facility_scope(
    structured_service: StructuredDataService,
) -> None:
    result = structured_service.chat_service_price(
        'Giá khám bệnh tại CS1 là bao nhiêu?',
        'Giá Khám bệnh',
        'CS1',
    )

    assert 'tại CS1 là 50.600 VND' in result.response
    assert 'CS1 và CS2' not in result.response
    records = result.metadata['structured_action']['records']
    assert {record['facility_code'] for record in records} == {'CS1'}


def test_bhyt_chat_uses_model_tier_override(
    structured_service: StructuredDataService,
) -> None:
    result = structured_service.chat_bhyt('BHYT năm, bậc?', '4')

    assert '683.100 VND' in result.response
    assert result.structured_record_ids[-1].endswith('TIER-04')


def test_ambiguous_duplicate_price_requires_user_selection(
    structured_service: StructuredDataService,
) -> None:
    result = structured_service.lookup_service_prices(
        query='Trích áp xe quanh Amidan',
        facility_code='CS1',
        as_of_date=None,
    )

    assert result.requires_clarification is True
    assert len({record.amount_vnd for record in result.records}) > 1


def test_schedule_endpoint_reads_approved_postgres_rows(
    structured_service: StructuredDataService,
) -> None:
    response = asyncio.run(
        _get(
            '/api/v1/schedules?week_start=2026-07-13'
            '&date=2026-07-17&facility_code=CS1'
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['records']
    assert all(row['service_date'] == '2026-07-17' for row in payload['records'])
    assert all(row['facility_code'] == 'CS1' for row in payload['records'])
    assert 'không đồng nghĩa còn suất' in payload['warning']


def test_pgvector_search_uses_seeded_1024_dimension_index(
    pg_session_factory: sessionmaker[Session],
) -> None:
    repository = PostgresStructuredRepository(pg_session_factory)
    rows = repository.search_embedded_knowledge_chunks(
        query_vector=[0.0] * 1_023 + [1.0],
        limit=3,
        minimum_score=-1.0,
    )

    assert len(rows) == 3
    assert all(row['embedding_dimension'] == 1_024 for row in rows)


def test_schedule_reference_clock_spans_future_weeks(
    pg_session_factory: sessionmaker[Session],
) -> None:
    repository = PostgresStructuredRepository(pg_session_factory)

    first_date, last_date = repository.schedule_date_range()

    assert first_date == date(2026, 6, 8)
    assert last_date == date(2026, 7, 19)
    assert last_date > first_date


def test_readiness_capacity_snapshot_is_safe(
    pg_session_factory: sessionmaker[Session],
) -> None:
    repository = PostgresStructuredRepository(pg_session_factory)
    snapshot = repository.readiness_snapshot(
        embedding_model='Vietnamese_Embedding',
        embedding_dimension=1_024,
        default_capacity=20,
        now=datetime.now(UTC),
    )

    assert snapshot.capacity_stats['over_capacity_sessions'] == 0
    assert snapshot.capacity_stats['unsafe_sessions'] == 0
    assert snapshot.counts['booking_sessions'] == 1_072
