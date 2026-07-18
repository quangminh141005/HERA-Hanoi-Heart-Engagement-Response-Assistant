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

    async def generate(self, messages, *, temperature=0.1, max_tokens=800):
        del messages, temperature, max_tokens
        raise RuntimeError("provider unavailable")


class StaticClient:
    provider_name = "static"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, messages, *, temperature=0.1, max_tokens=800):
        del messages, temperature, max_tokens
        self.calls += 1
        return "fallback answer"


class SlowClient:
    provider_name = "slow"

    async def generate(self, messages, *, temperature=0.1, max_tokens=800):
        del messages, temperature, max_tokens
        await asyncio.sleep(0.05)
        return "slow answer"


class CapturedClient:
    def __init__(self, *, api_key: str, model: str, **kwargs):
        self.api_key = api_key
        self.model = model
        self.kwargs = kwargs

    async def generate(self, messages, *, temperature=0.1, max_tokens=800):
        del messages, temperature, max_tokens
        return self.model


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
    assert client.client.clients[0].model == "gpt-oss-20b"
    assert client.client.clients[0].kwargs["base_url"] == "https://mkp-api.fptcloud.com"


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
