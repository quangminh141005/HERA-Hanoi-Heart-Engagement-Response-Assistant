'''Tests for the PII-safe, cross-replica structured Redis cache.'''

from __future__ import annotations

import json

from app.structured.cache import RedisStructuredQueryCache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.closed = False

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.expirations[key] = ex

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        self.closed = True


def test_cache_is_cross_replica_and_never_exposes_query_in_key_or_value() -> None:
    redis = FakeRedis()
    writer = RedisStructuredQueryCache(
        redis_url='redis://unused',
        ttl_seconds=120,
        client=redis,
    )
    reader = RedisStructuredQueryCache(
        redis_url='redis://unused',
        ttl_seconds=120,
        client=redis,
    )
    sensitive_query = 'giá khám 0912345678 patient@example.com'
    identity = {'query': sensitive_query, 'facility_code': 'CS1'}
    official_rows = [
        {
            'service_record_id': 'SERVICE-1',
            'amount_vnd': 50_600,
            'facility_code': 'CS1',
        }
    ]

    writer.set('service-prices', identity, official_rows)

    assert len(redis.values) == 1
    key, raw = next(iter(redis.values.items()))
    assert key.startswith('hera:structured:v1:service-prices:')
    assert sensitive_query not in key
    assert '0912345678' not in key
    assert 'patient@example.com' not in key
    assert sensitive_query not in raw
    assert json.loads(raw) == official_rows
    assert redis.expirations[key] == 120
    assert reader.get('service-prices', identity) == official_rows
    assert reader.ping() is True

    reader.close()
    assert redis.closed is True


class BrokenRedis:
    def get(self, key: str):
        del key
        raise ConnectionError('private redis detail')

    def set(self, key: str, value: str, *, ex: int):
        del key, value, ex
        raise ConnectionError('private redis detail')

    def ping(self) -> bool:
        raise ConnectionError('private redis detail')

    def close(self) -> None:
        return None


def test_cache_failure_is_fail_open() -> None:
    cache = RedisStructuredQueryCache(
        redis_url='redis://unused',
        client=BrokenRedis(),
    )

    assert cache.get('schedules', {'week': 'current'}) is None
    cache.set('schedules', {'week': 'current'}, [{'record_id': 'SCHEDULE-1'}])
    assert cache.ping() is False


def test_oversized_value_is_not_cached() -> None:
    redis = FakeRedis()
    cache = RedisStructuredQueryCache(
        redis_url='redis://unused',
        max_payload_bytes=1_024,
        client=redis,
    )

    cache.set('schedules', {'week': 'current'}, [{'value': 'x' * 2_000}])

    assert redis.values == {}
