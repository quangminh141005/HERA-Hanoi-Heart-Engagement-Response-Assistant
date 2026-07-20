"""LLM client configuration tests."""

from __future__ import annotations

import asyncio

from app.ai.llm import client as llm_client_module
from app.ai.llm.client import (
    FallbackLLMClient,
    GuardedLLMClient,
    NoopLLMClient,
    build_llm_client,
)
from app.core.config import Settings


class FailingClient:
    provider_name = "openai"

    async def generate(self, messages, *, temperature=0.1, max_tokens=1024):
        del messages, temperature, max_tokens
        raise RuntimeError("provider unavailable")


class StaticClient:
    provider_name = "static"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, messages, *, temperature=0.1, max_tokens=1024):
        del messages, temperature, max_tokens
        self.calls += 1
        return "fallback answer"


class SlowClient:
    provider_name = "slow"

    async def generate(self, messages, *, temperature=0.1, max_tokens=1024):
        del messages, temperature, max_tokens
        await asyncio.sleep(0.05)
        return "slow answer"


class CapturedClient:
    def __init__(self, *, api_key: str, model: str, **kwargs):
        self.api_key = api_key
        self.model = model
        self.kwargs = kwargs

    async def generate(self, messages, *, temperature=0.1, max_tokens=1024):
        del messages, temperature, max_tokens
        return self.model


class ReleaseFailingGate:
    def __init__(self) -> None:
        self.release_calls = 0

    async def acquire(self, *, timeout_seconds: float) -> str:
        del timeout_seconds
        return "lease-token"

    async def release(self, token: str) -> None:
        assert token == "lease-token"
        self.release_calls += 1
        raise RuntimeError("redis unavailable during release")


def test_build_llm_client_without_keys_returns_noop() -> None:
    settings = Settings(
        LLM_PROVIDER="openai",
        OPENAI_API_KEY=None,
        _env_file=None,
    )

    client = build_llm_client(settings)

    assert isinstance(client, NoopLLMClient)


def test_build_llm_client_uses_only_configured_openai_compatible_provider(
    monkeypatch,
) -> None:
    monkeypatch.setattr(llm_client_module, "OpenAILLMClient", CapturedClient)
    settings = Settings(
        LLM_PROVIDER="openai",
        OPENAI_API_KEY="openai-key",
        OPENAI_MODEL="openai-model",
        _env_file=None,
    )

    client = build_llm_client(settings)

    assert isinstance(client, GuardedLLMClient)
    assert isinstance(client.client, FallbackLLMClient)
    assert [provider.model for provider in client.client.clients] == ["openai-model"]
    assert [provider.api_key for provider in client.client.clients] == ["openai-key"]


def test_fpt_shared_key_selects_required_models(monkeypatch) -> None:
    monkeypatch.setattr(llm_client_module, "OpenAILLMClient", CapturedClient)
    settings = Settings(
        LLM_PROVIDER="openai",
        API_KEY="shared-fpt-key",
        OPENAI_API_KEY=None,
        _env_file=None,
    )

    client = build_llm_client(settings)

    assert isinstance(client, GuardedLLMClient)
    assert isinstance(client.client, FallbackLLMClient)
    assert client.client.clients[0].model == "gpt-oss-120b"
    assert client.client.clients[0].kwargs["base_url"] == "https://mkp-api.fptcloud.com"


def test_fpt_shared_key_accepts_guard_model_override(monkeypatch) -> None:
    monkeypatch.setattr(llm_client_module, "OpenAILLMClient", CapturedClient)
    settings = Settings(
        LLM_PROVIDER="openai",
        API_KEY="shared-fpt-key",
        OPENAI_API_KEY=None,
        _env_file=None,
    )

    client = build_llm_client(
        settings,
        model_override="gpt-oss-20b",
        provider_label_override="fpt_guard",
    )

    assert isinstance(client, GuardedLLMClient)
    assert isinstance(client.client, FallbackLLMClient)
    assert client.client.clients[0].model == "gpt-oss-20b"
    assert client.client.clients[0].kwargs["provider_label"] == "fpt_guard"


def test_fallback_llm_client_can_use_injected_secondary_client() -> None:
    client = FallbackLLMClient([FailingClient(), StaticClient()])

    answer = asyncio.run(client.generate([{"role": "user", "content": "hello"}]))

    assert answer == "fallback answer"


def test_guarded_llm_client_caches_duplicate_responses() -> None:
    static = StaticClient()
    client = GuardedLLMClient(
        static,
        max_concurrent_requests=1,
        queue_timeout_seconds=0.01,
        cache_enabled=True,
        cache_ttl_seconds=60,
        cache_max_entries=10,
    )
    messages = [{"role": "user", "content": "repeat"}]

    first = asyncio.run(client.generate(messages, temperature=0.0, max_tokens=12))
    second = asyncio.run(client.generate(messages, temperature=0.0, max_tokens=12))

    assert first == "fallback answer"
    assert second == "fallback answer"
    assert static.calls == 1


def test_guarded_llm_client_queue_timeout_returns_safe_fallback() -> None:
    client = GuardedLLMClient(
        SlowClient(),
        max_concurrent_requests=1,
        queue_timeout_seconds=0.001,
        cache_enabled=False,
        cache_ttl_seconds=60,
        cache_max_entries=10,
    )

    async def run_two_requests() -> tuple[str, str]:
        first = asyncio.create_task(
            client.generate([{"role": "user", "content": "first"}])
        )
        await asyncio.sleep(0)
        second = asyncio.create_task(
            client.generate([{"role": "user", "content": "second"}])
        )
        return await first, await second

    first, second = asyncio.run(run_two_requests())

    assert first == "slow answer"
    assert second.startswith("HERA chưa được cấu hình LLM")


def test_guarded_llm_client_release_failure_keeps_response_and_semaphore() -> None:
    static = StaticClient()
    gate = ReleaseFailingGate()
    client = GuardedLLMClient(
        static,
        max_concurrent_requests=1,
        queue_timeout_seconds=0.01,
        cache_enabled=False,
        cache_ttl_seconds=60,
        cache_max_entries=10,
        distributed_gate=gate,
    )

    async def run_sequential_requests() -> tuple[str, str]:
        first = await client.generate([{"role": "user", "content": "first"}])
        second = await client.generate([{"role": "user", "content": "second"}])
        return first, second

    first, second = asyncio.run(run_sequential_requests())

    assert first == "fallback answer"
    assert second == "fallback answer"
    assert static.calls == 2
    assert gate.release_calls == 2
