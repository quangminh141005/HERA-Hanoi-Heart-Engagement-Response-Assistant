"""Unit tests for the gateway token-bucket implementation."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.core.config import Settings
from app.core.rate_limit import (
    RateLimitPolicy,
    TokenBucketRateLimiter,
    get_gateway_rate_limit_policy,
)
from pydantic import ValidationError


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

    def test_production_rejects_process_local_storage(self):
        with self.assertRaises(ValidationError):
            Settings(
                DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
                APP_DEBUG=False,
                RATE_LIMIT_ENABLED=True,
                RATE_LIMIT_STORAGE="memory",
                _env_file=None,
            )


if __name__ == "__main__":
    unittest.main()

