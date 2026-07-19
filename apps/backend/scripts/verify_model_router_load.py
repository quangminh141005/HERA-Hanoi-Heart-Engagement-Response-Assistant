"""Verify the Redis model gate across independent clients without model calls."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ai.llm.client import RedisModelConcurrencyGate  # noqa: E402
from app.core.config import get_settings  # noqa: E402


async def main() -> int:
    settings = get_settings()
    limit = settings.LLM_GLOBAL_MAX_CONCURRENT_REQUESTS
    gates = [
        RedisModelConcurrencyGate(
            redis_url=settings.REDIS_URL,
            gate_name="load-check",
            limit=limit,
            lease_seconds=10,
        )
        for _ in range(2)
    ]
    active = 0
    peak = 0
    completed = 0
    lock = asyncio.Lock()

    async def worker(index: int) -> None:
        nonlocal active, peak, completed
        gate = gates[index % len(gates)]
        token = await gate.acquire(timeout_seconds=5)
        if token is None:
            raise RuntimeError("model gate timed out during load verification")
        try:
            async with lock:
                active += 1
                peak = max(peak, active)
            await asyncio.sleep(0.025)
            async with lock:
                active -= 1
                completed += 1
        finally:
            await gate.release(token)

    try:
        await asyncio.gather(*(worker(index) for index in range(limit * 5)))
    finally:
        await asyncio.gather(*(gate.close() for gate in gates))
    passed = completed == limit * 5 and peak <= limit
    print(json.dumps({"passed": passed, "limit": limit, "peak": peak, "completed": completed}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
