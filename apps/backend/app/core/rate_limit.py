"""Gateway token-bucket rate limiting."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from math import floor
from threading import Lock
from time import monotonic
from typing import Literal, Protocol

from fastapi import Request

from app.core.config import Settings

IdentityType = Literal["ip"]


@dataclass(frozen=True)
class RateLimitPolicy:
    """A route policy expressed as requests per window."""

    name: str
    requests: int
    window_seconds: int
    identity: IdentityType = "ip"

    @property
    def refill_rate(self) -> float:
        return self.requests / self.window_seconds


@dataclass
class TokenBucket:
    """Mutable in-memory bucket state."""

    tokens: float
    updated_at: float
    last_seen_at: float


@dataclass(frozen=True)
class RateLimitDecision:
    """Quota state returned to middleware."""

    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset_after: int


class RateLimitStore(Protocol):
    """Storage contract shared by local-memory and Redis stores."""

    async def startup(self) -> None:
        """Initialize and verify the store."""

    async def ping(self) -> bool:
        """Return whether the store is reachable right now."""

    async def consume(
        self,
        key: str,
        policy: RateLimitPolicy,
        now: float | None = None,
    ) -> RateLimitDecision:
        """Atomically consume one token."""

    async def close(self) -> None:
        """Release resources."""


class InMemoryTokenBucketStore:
    """Thread-safe development store for one backend process."""

    def __init__(self, stale_after_seconds: int = 3600):
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = Lock()
        self._stale_after_seconds = stale_after_seconds
        self._checks_since_cleanup = 0

    async def startup(self) -> None:
        return None

    async def ping(self) -> bool:
        return True

    async def consume(
        self,
        key: str,
        policy: RateLimitPolicy,
        now: float | None = None,
    ) -> RateLimitDecision:
        current_time = monotonic() if now is None else now

        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(
                    tokens=float(policy.requests),
                    updated_at=current_time,
                    last_seen_at=current_time,
                )
                self._buckets[key] = bucket

            elapsed = max(0.0, current_time - bucket.updated_at)
            bucket.tokens = min(
                float(policy.requests),
                bucket.tokens + elapsed * policy.refill_rate,
            )
            bucket.updated_at = current_time
            bucket.last_seen_at = current_time

            allowed = bucket.tokens >= 1
            if allowed:
                bucket.tokens -= 1

            self._checks_since_cleanup += 1
            if self._checks_since_cleanup >= 1000:
                self._remove_stale_buckets(current_time)

            return _build_decision(bucket.tokens, policy, allowed)

    async def close(self) -> None:
        self._buckets.clear()

    def _remove_stale_buckets(self, current_time: float) -> None:
        cutoff = current_time - self._stale_after_seconds
        stale_keys = [
            key
            for key, bucket in self._buckets.items()
            if bucket.last_seen_at < cutoff
        ]
        for key in stale_keys:
            del self._buckets[key]
        self._checks_since_cleanup = 0


class RedisTokenBucketStore:
    """Atomic Redis token bucket shared by backend workers."""

    _CONSUME_SCRIPT = """
local bucket_key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local redis_time = redis.call('TIME')
local now = tonumber(redis_time[1]) + tonumber(redis_time[2]) / 1000000
local values = redis.call('HMGET', bucket_key, 'tokens', 'updated_at')
local tokens = tonumber(values[1])
local updated_at = tonumber(values[2])

if tokens == nil then
    tokens = capacity
    updated_at = now
end

local elapsed = math.max(0, now - updated_at)
tokens = math.min(capacity, tokens + elapsed * refill_rate)
local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

redis.call('HSET', bucket_key, 'tokens', tokens, 'updated_at', now)
redis.call('EXPIRE', bucket_key, ttl)

local missing = math.max(0, 1 - tokens)
local retry_after = 0
if allowed == 0 then
    retry_after = math.max(1, math.ceil(missing / refill_rate))
end
local reset_after = math.ceil((capacity - tokens) / refill_rate)

return {allowed, tostring(tokens), retry_after, reset_after}
"""

    def __init__(self, redis_url: str):
        try:
            from redis.asyncio import Redis
        except ImportError as exc:
            raise RuntimeError("Redis rate limiting requires redis") from exc

        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._script = self._client.register_script(self._CONSUME_SCRIPT)

    async def startup(self) -> None:
        await self._client.ping()

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    async def consume(
        self,
        key: str,
        policy: RateLimitPolicy,
        now: float | None = None,
    ) -> RateLimitDecision:
        del now
        ttl = max(policy.window_seconds * 2, 60)
        result = await self._script(
            keys=[f"rate-limit:{key}"],
            args=[policy.requests, policy.refill_rate, ttl],
        )
        allowed = bool(int(result[0]))
        tokens = float(result[1])
        return RateLimitDecision(
            allowed=allowed,
            limit=policy.requests,
            remaining=max(0, floor(tokens)),
            retry_after=int(result[2]),
            reset_after=max(0, int(result[3])),
        )

    async def close(self) -> None:
        await self._client.aclose()


class TokenBucketRateLimiter:
    """Application wrapper for the configured bucket store."""

    def __init__(self, store: RateLimitStore | None = None):
        self.store = store or InMemoryTokenBucketStore()

    async def startup(self) -> None:
        await self.store.startup()

    async def ping(self) -> bool:
        return await self.store.ping()

    async def consume(
        self,
        key: str,
        policy: RateLimitPolicy,
        now: float | None = None,
    ) -> RateLimitDecision:
        return await self.store.consume(key, policy, now)

    async def close(self) -> None:
        await self.store.close()


def create_rate_limiter(settings: Settings) -> TokenBucketRateLimiter:
    """Build the configured rate limiter without opening app routes."""

    if not settings.RATE_LIMIT_ENABLED:
        return TokenBucketRateLimiter(InMemoryTokenBucketStore())
    if settings.RATE_LIMIT_STORAGE == "redis":
        return TokenBucketRateLimiter(RedisTokenBucketStore(settings.REDIS_URL))
    return TokenBucketRateLimiter(InMemoryTokenBucketStore())


def get_gateway_rate_limit_policy(
    method: str,
    path: str,
    settings: Settings,
) -> RateLimitPolicy | None:
    """Resolve IP policies enforced at the gateway boundary."""

    normalized_method = method.upper()
    api_prefix = settings.API_V1_STR.rstrip("/")
    if normalized_method == "OPTIONS":
        return None
    health_paths = {
        "/health",
        "/healthz",
        "/readyz",
        settings.PROMETHEUS_METRICS_PATH,
        f"{api_prefix}/health",
        f"{api_prefix}/health/db",
        f"{api_prefix}/health/ready",
    }
    if path in health_paths:
        return RateLimitPolicy(
            "health",
            settings.RATE_LIMIT_HEALTH_PER_MINUTE,
            60,
        )
    if not path.startswith(api_prefix):
        return None
    if normalized_method == "POST" and path == f"{api_prefix}/chat":
        return RateLimitPolicy("chat", settings.RATE_LIMIT_CHAT_PER_MINUTE, 60)
    return RateLimitPolicy(
        "gateway-default",
        settings.RATE_LIMIT_DEFAULT_PER_MINUTE,
        60,
    )


def get_gateway_rate_limit_key(
    request: Request,
    policy: RateLimitPolicy,
    *,
    trust_proxy_headers: bool = False,
    trusted_proxy_cidrs: tuple[str, ...] | list[str] = (),
) -> str:
    """Build the quota identity key for a request."""

    client_host = request.client.host if request.client else "unknown"
    if trust_proxy_headers and _peer_is_trusted_proxy(
        client_host,
        trusted_proxy_cidrs,
    ):
        forwarded_host = request.headers.get("X-Real-IP", "").strip()
        try:
            client_host = str(ip_address(forwarded_host))
        except ValueError:
            pass
    return f"{policy.name}:{policy.identity}:{client_host}"


def _peer_is_trusted_proxy(
    peer_host: str,
    trusted_proxy_cidrs: tuple[str, ...] | list[str],
) -> bool:
    try:
        peer = ip_address(peer_host)
    except ValueError:
        return False
    for cidr in trusted_proxy_cidrs:
        try:
            if peer in ip_network(cidr, strict=False):
                return True
        except ValueError:
            # Settings validates configured networks. Keep the boundary safe if a
            # lightweight test double or future caller bypasses Settings.
            continue
    return False


def _build_decision(
    tokens: float,
    policy: RateLimitPolicy,
    allowed: bool,
) -> RateLimitDecision:
    if allowed:
        retry_after = 0
    else:
        missing = max(0.0, 1.0 - tokens)
        retry_after = max(1, int((missing / policy.refill_rate) + 0.999))
    reset_after = max(0, int(((policy.requests - tokens) / policy.refill_rate) + 0.999))
    return RateLimitDecision(
        allowed=allowed,
        limit=policy.requests,
        remaining=max(0, floor(tokens)),
        retry_after=retry_after,
        reset_after=reset_after,
    )

