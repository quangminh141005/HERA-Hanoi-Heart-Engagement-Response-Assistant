'''Fail-open Redis cache for immutable approved structured query rows.'''

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Protocol

from app.observability.prometheus import STRUCTURED_CACHE_OPERATIONS_TOTAL

logger = logging.getLogger(__name__)


class StructuredQueryCache(Protocol):
    '''Cache contract. Callers must only store approved official rows.'''

    def get(self, namespace: str, identity: Mapping[str, object]) -> Any | None: ...

    def set(
        self,
        namespace: str,
        identity: Mapping[str, object],
        value: object,
    ) -> None: ...

    def ping(self) -> bool: ...

    def close(self) -> None: ...


class NoopStructuredQueryCache:
    '''Disabled cache used by local unit tests and explicit fail-closed setups.'''

    def get(self, namespace: str, identity: Mapping[str, object]) -> None:
        del namespace, identity
        return None

    def set(
        self,
        namespace: str,
        identity: Mapping[str, object],
        value: object,
    ) -> None:
        del namespace, identity, value

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None


class RedisStructuredQueryCache:
    '''Cross-replica cache with hashed keys and bounded JSON values.'''

    def __init__(
        self,
        *,
        redis_url: str,
        ttl_seconds: int = 300,
        max_payload_bytes: int = 524_288,
        client: Any | None = None,
    ) -> None:
        self._ttl_seconds = max(1, ttl_seconds)
        self._max_payload_bytes = max(1_024, max_payload_bytes)
        if client is not None:
            self._client = client
            return
        from redis import Redis

        self._client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
            retry_on_timeout=False,
            health_check_interval=30,
            max_connections=10,
        )

    def get(self, namespace: str, identity: Mapping[str, object]) -> Any | None:
        try:
            raw = self._client.get(_cache_key(namespace, identity))
            if not raw:
                STRUCTURED_CACHE_OPERATIONS_TOTAL.labels(result='miss').inc()
                return None
            value = json.loads(raw)
            STRUCTURED_CACHE_OPERATIONS_TOTAL.labels(result='hit').inc()
            return value
        except Exception as exc:
            STRUCTURED_CACHE_OPERATIONS_TOTAL.labels(result='error').inc()
            logger.warning(
                'structured cache read failed; querying PostgreSQL',
                extra={
                    'event': 'structured_cache_read_failed',
                    'error_type': exc.__class__.__name__,
                },
            )
            return None

    def set(
        self,
        namespace: str,
        identity: Mapping[str, object],
        value: object,
    ) -> None:
        try:
            payload = json.dumps(
                value,
                ensure_ascii=False,
                separators=(',', ':'),
                default=_json_default,
            )
            if len(payload.encode('utf-8')) > self._max_payload_bytes:
                STRUCTURED_CACHE_OPERATIONS_TOTAL.labels(result='skipped').inc()
                return
            self._client.set(
                _cache_key(namespace, identity),
                payload,
                ex=self._ttl_seconds,
            )
            STRUCTURED_CACHE_OPERATIONS_TOTAL.labels(result='write').inc()
        except Exception as exc:
            STRUCTURED_CACHE_OPERATIONS_TOTAL.labels(result='error').inc()
            logger.warning(
                'structured cache write failed; response remains available',
                extra={
                    'event': 'structured_cache_write_failed',
                    'error_type': exc.__class__.__name__,
                },
            )

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            return None


def build_structured_query_cache(settings) -> StructuredQueryCache:
    '''Build the configured cache without placing secrets in keys or logs.'''

    if not settings.STRUCTURED_CACHE_ENABLED:
        return NoopStructuredQueryCache()
    return RedisStructuredQueryCache(
        redis_url=settings.REDIS_URL,
        ttl_seconds=settings.STRUCTURED_CACHE_TTL_SECONDS,
        max_payload_bytes=settings.STRUCTURED_CACHE_MAX_PAYLOAD_BYTES,
    )


def _cache_key(namespace: str, identity: Mapping[str, object]) -> str:
    safe_namespace = ''.join(
        char for char in namespace.lower() if char.isalnum() or char in '-_'
    )[:48]
    canonical = json.dumps(
        dict(identity),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        default=_json_default,
    )
    digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    namespace_value = safe_namespace or 'query'
    return f'hera:structured:v1:{namespace_value}:{digest}'


def _json_default(value: object) -> str:
    if isinstance(value, date | datetime):
        return value.isoformat()
    raise TypeError(f'Unsupported cache value: {type(value).__name__}')
