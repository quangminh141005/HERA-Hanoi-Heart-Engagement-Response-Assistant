"""Unit tests for the gateway token-bucket implementation."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.core.config import Settings
from app.core.rate_limit import (
    InMemoryTokenBucketStore,
    RateLimitPolicy,
    TokenBucketRateLimiter,
    create_rate_limiter,
    get_gateway_rate_limit_key,
    get_gateway_rate_limit_policy,
)
from pydantic import ValidationError
from starlette.requests import Request


class TokenBucketRateLimiterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.policy = RateLimitPolicy(name="test", requests=2, window_seconds=10)
        self.limiter = TokenBucketRateLimiter()

    async def test_rejects_after_capacity_is_consumed(self):
        first = await self.limiter.consume("test:ip:127.0.0.1", self.policy, now=0)
        second = await self.limiter.consume("test:ip:127.0.0.1", self.policy, now=0)
        third = await self.limiter.consume("test:ip:127.0.0.1", self.policy, now=0)

        self.assertTrue(first.allowed)
        self.assertTrue(second.allowed)
        self.assertFalse(third.allowed)
        self.assertEqual(third.retry_after, 5)

    async def test_refills_tokens_over_time(self):
        key = "test:ip:127.0.0.1"
        await self.limiter.consume(key, self.policy, now=0)
        await self.limiter.consume(key, self.policy, now=0)

        decision = await self.limiter.consume(key, self.policy, now=5)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.remaining, 0)

    def test_gateway_policy_is_ip_based(self):
        settings = SimpleNamespace(
            API_V1_STR="/api/v1",
            PROMETHEUS_METRICS_PATH="/metrics",
            RATE_LIMIT_HEALTH_PER_MINUTE=300,
            RATE_LIMIT_CHAT_PER_MINUTE=30,
            RATE_LIMIT_DEFAULT_PER_MINUTE=120,
        )

        policy = get_gateway_rate_limit_policy("POST", "/api/v1/chat", settings)

        self.assertIsNotNone(policy)
        self.assertEqual(policy.name, "chat")
        self.assertEqual(policy.identity, "ip")

        readiness_policy = get_gateway_rate_limit_policy("GET", "/readyz", settings)
        self.assertIsNotNone(readiness_policy)
        self.assertEqual(readiness_policy.name, "health")

    def test_disabled_rate_limiting_does_not_connect_to_redis(self):
        settings = Settings(
            RATE_LIMIT_ENABLED=False,
            RATE_LIMIT_STORAGE="redis",
            _env_file=None,
        )

        limiter = create_rate_limiter(settings)

        self.assertIsInstance(limiter.store, InMemoryTokenBucketStore)

    def test_production_rejects_process_local_storage(self):
        with self.assertRaises(ValidationError):
            Settings(
                DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
                APP_DEBUG=False,
                RATE_LIMIT_ENABLED=True,
                RATE_LIMIT_STORAGE="memory",
                _env_file=None,
            )

    def test_trusted_proxy_uses_validated_real_ip(self):
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/chat",
                "headers": [(b"x-real-ip", b"203.0.113.8")],
                "client": ("172.20.0.4", 12345),
            }
        )

        key = get_gateway_rate_limit_key(
            request,
            self.policy,
            trust_proxy_headers=True,
            trusted_proxy_cidrs=["172.20.0.0/16"],
        )

        self.assertEqual(key, "test:ip:203.0.113.8")

    def test_untrusted_or_invalid_proxy_header_uses_peer_ip(self):
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/chat",
                "headers": [(b"x-real-ip", b"not-an-ip")],
                "client": ("172.20.0.4", 12345),
            }
        )

        key = get_gateway_rate_limit_key(
            request,
            self.policy,
            trust_proxy_headers=True,
            trusted_proxy_cidrs=["172.20.0.0/16"],
        )

        self.assertEqual(key, "test:ip:172.20.0.4")

    def test_valid_forwarded_ip_from_untrusted_peer_is_ignored(self):
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/chat",
                "headers": [(b"x-real-ip", b"203.0.113.8")],
                "client": ("198.51.100.4", 12345),
            }
        )

        key = get_gateway_rate_limit_key(
            request,
            self.policy,
            trust_proxy_headers=True,
            trusted_proxy_cidrs=["172.20.0.0/16"],
        )

        self.assertEqual(key, "test:ip:198.51.100.4")


if __name__ == "__main__":
    unittest.main()

