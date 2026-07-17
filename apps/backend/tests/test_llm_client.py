"""LLM client configuration tests."""

from __future__ import annotations

import asyncio

from app.ai.llm import client as llm_client_module
from app.ai.llm.client import FallbackLLMClient, NoopLLMClient, build_llm_client
from app.core.config import Settings


class FailingClient:
    provider_name = "openai"

    async def generate(self, messages, *, temperature=0.1, max_tokens=800):
        del messages, temperature, max_tokens
        raise RuntimeError("provider unavailable")


class StaticClient:
    provider_name = "gemini"

    async def generate(self, messages, *, temperature=0.1, max_tokens=800):
        del messages, temperature, max_tokens
        return "fallback answer"


class CapturedClient:
    def __init__(self, *, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def generate(self, messages, *, temperature=0.1, max_tokens=800):
        del messages, temperature, max_tokens
        return self.model


def test_build_llm_client_without_keys_returns_noop() -> None:
    settings = Settings(
        LLM_PROVIDER="openai",
        LLM_FALLBACK_PROVIDER="gemini",
        OPENAI_API_KEY=None,
        GEMINI_API_KEY=None,
        _env_file=None,
    )

    client = build_llm_client(settings)

    assert isinstance(client, NoopLLMClient)


def test_build_llm_client_uses_openai_then_gemini(monkeypatch) -> None:
    monkeypatch.setattr(llm_client_module, "OpenAILLMClient", CapturedClient)
    monkeypatch.setattr(llm_client_module, "GeminiLLMClient", CapturedClient)
    settings = Settings(
        LLM_PROVIDER="openai",
        LLM_FALLBACK_PROVIDER="gemini",
        OPENAI_API_KEY="openai-key",
        OPENAI_MODEL="openai-model",
        GEMINI_API_KEY="gemini-key",
        GEMINI_MODEL="gemini-model",
        _env_file=None,
    )

    client = build_llm_client(settings)

    assert isinstance(client, FallbackLLMClient)
    assert [provider.model for provider in client.clients] == [
        "openai-model",
        "gemini-model",
    ]
    assert [provider.api_key for provider in client.clients] == [
        "openai-key",
        "gemini-key",
    ]


def test_fallback_llm_client_uses_gemini_when_openai_fails() -> None:
    client = FallbackLLMClient([FailingClient(), StaticClient()])

    answer = asyncio.run(client.generate([{"role": "user", "content": "hello"}]))

    assert answer == "fallback answer"
