"""Bounded metrics and provider-client safety tests."""

from __future__ import annotations

from types import SimpleNamespace

import openai
from app.ai.llm.client import OpenAILLMClient
from app.ai.rag.embeddings.embedder import OpenAICompatibleEmbedder
from app.observability.prometheus import (
    UPSTREAM_FAILURES_TOTAL,
    UPSTREAM_TIMEOUTS_TOTAL,
    record_upstream_failure,
)


def test_wrapped_timeout_is_counted_under_bounded_unknown_provider() -> None:
    failure = UPSTREAM_FAILURES_TOTAL.labels(provider="unknown")
    timeout = UPSTREAM_TIMEOUTS_TOTAL.labels(provider="unknown")
    failures_before = failure._value.get()
    timeouts_before = timeout._value.get()
    try:
        raise TimeoutError("synthetic timeout")
    except TimeoutError as cause:
        wrapped = RuntimeError("synthetic wrapper")
        wrapped.__cause__ = cause

    record_upstream_failure("request-controlled-provider", wrapped)

    assert failure._value.get() == failures_before + 1
    assert timeout._value.get() == timeouts_before + 1


def test_fpt_clients_disable_hidden_sdk_retries(monkeypatch) -> None:
    captured: list[dict] = []

    def fake_async_openai(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(openai, "AsyncOpenAI", fake_async_openai)

    OpenAILLMClient(
        api_key="mock",
        model="gpt-oss-120b",
        base_url="https://example.invalid",
        timeout_seconds=1,
    )
    OpenAICompatibleEmbedder(
        api_key="mock",
        model="Vietnamese_Embedding",
        base_url="https://example.invalid",
        timeout_seconds=1,
    )

    assert [item["max_retries"] for item in captured] == [0, 0]
