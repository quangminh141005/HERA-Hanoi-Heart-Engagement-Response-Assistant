"""Local-only release-gate tests; no provider request is made here."""

from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.services.health import collect_runtime_readiness


class FakeRateLimiter:
    async def ping(self) -> bool:
        return True


def _release_settings(**overrides) -> Settings:
    values = {
        "API_KEY": "mock-key-that-is-never-sent",
        "RATE_LIMIT_ENABLED": True,
        "RATE_LIMIT_STORAGE": "redis",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_runtime_readiness_names_redis_and_database_migration() -> None:
    checks = asyncio.run(
        collect_runtime_readiness(
            _release_settings(),
            FakeRateLimiter(),
            database_probe=lambda: (True, True),
        )
    )

    assert checks == {
        "rate_limit_store": True,
        "postgresql": True,
        "database_migration": True,
        "redis": True,
    }
