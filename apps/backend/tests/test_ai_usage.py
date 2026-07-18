"""Provider token accounting, cost metrics and metadata-only tracing tests."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from app.ai.llm import client as llm_client_module
from app.ai.llm.client import OpenAILLMClient
from app.ai.rag.embeddings import embedder as embedder_module
from app.ai.rag.embeddings.embedder import OpenAICompatibleEmbedder
from app.core.config import Settings
from app.observability.ai_usage import (
    extract_openai_embedding_usage,
    extract_openai_usage,
)
from app.observability.prometheus import AI_TOKENS_TOTAL


class _CapturedObservation:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class _FakeChatSdk:
    def __init__(self, response) -> None:
        self.response = response
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs):
        del kwargs
        return self.response


class _FakeEmbeddingSdk:
    def __init__(self, response) -> None:
        self.response = response
        self.embeddings = self

    async def create(self, **kwargs):
        del kwargs
        return self.response


def test_usage_aliases_and_reasoning_are_normalized_without_double_counting() -> None:
    response = {
        "usage": {
            "input_tokens": 100,
            "output_tokens": 25,
            "output_tokens_details": {"reasoning_tokens": 10},
            "total_tokens": 125,
        }
    }

    usage = extract_openai_usage(response)

    assert usage.input_tokens == 100
    assert usage.output_tokens == 25
    assert usage.reasoning_tokens == 10


def test_reasoning_and_embedding_total_are_counted_when_primary_fields_are_absent() -> None:
    llm_usage = extract_openai_usage(
        SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=7,
                reasoning_tokens=12,
            )
        )
    )
    embedding_usage = extract_openai_embedding_usage(
        SimpleNamespace(usage=SimpleNamespace(total_tokens=31))
    )

    assert llm_usage.output_tokens == 12
    assert embedding_usage.input_tokens == 31
    assert embedding_usage.output_tokens == 0


def test_llm_records_provider_usage_and_scalar_langfuse_metadata(
    monkeypatch,
) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))],
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=25,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=10),
            total_tokens=125,
        ),
    )
    observation = _CapturedObservation()

    @contextmanager
    def fake_observation(*args, **kwargs):
        del args, kwargs
        yield observation

    monkeypatch.setattr(llm_client_module, "start_observation", fake_observation)
    settings = Settings(_env_file=None)
    input_metric = AI_TOKENS_TOTAL.labels(provider="fpt_llm", kind="input")
    output_metric = AI_TOKENS_TOTAL.labels(provider="fpt_llm", kind="output")
    input_before = input_metric._value.get()
    output_before = output_metric._value.get()
    client = OpenAILLMClient(
        api_key="test",
        model="gpt-oss-120b",
        provider_label="fpt_llm",
        sdk_client=_FakeChatSdk(response),
        settings=settings,
    )

    answer = asyncio.run(client.generate([{"role": "user", "content": "safe"}]))

    assert answer == "answer"
    assert input_metric._value.get() - input_before == 100
    assert output_metric._value.get() - output_before == 25
    usage_update = observation.updates[0]["metadata"]
    assert usage_update == {
        "input_tokens": 100,
        "output_tokens": 25,
    }
    assert all(isinstance(value, str | int | float | bool) for value in usage_update.values())


def test_llm_content_capture_records_messages_output_and_usage_details(
    monkeypatch,
) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))],
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=125,
        ),
    )
    observation = _CapturedObservation()
    start_kwargs = {}

    @contextmanager
    def fake_observation(name, **kwargs):
        start_kwargs["name"] = name
        start_kwargs.update(kwargs)
        yield observation

    monkeypatch.setattr(llm_client_module, "start_observation", fake_observation)
    settings = Settings(
        LANGFUSE_CAPTURE_CONTENT=True,
        _env_file=None,
    )
    messages = [{"role": "user", "content": "safe"}]
    client = OpenAILLMClient(
        api_key="test",
        model="gpt-oss-120b",
        provider_label="fpt_llm",
        sdk_client=_FakeChatSdk(response),
        settings=settings,
    )

    answer = asyncio.run(client.generate(messages, temperature=0.0, max_tokens=1024))

    assert answer == "answer"
    assert start_kwargs["name"] == "hera.llm.provider_call"
    assert start_kwargs["input"] == messages
    assert start_kwargs["model"] == "gpt-oss-120b"
    assert start_kwargs["model_parameters"] == {
        "temperature": 0.0,
        "max_tokens": 1024,
    }
    usage_update = observation.updates[0]
    assert usage_update["output"] == "answer"
    assert usage_update["usage_details"] == {
        "input": 100,
        "output": 25,
        "total": 125,
    }


def test_embedding_records_provider_input_tokens() -> None:
    response = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])],
        usage=SimpleNamespace(prompt_tokens=40, total_tokens=40),
    )
    token_metric = AI_TOKENS_TOTAL.labels(provider="fpt_embedding", kind="input")
    tokens_before = token_metric._value.get()
    embedder = OpenAICompatibleEmbedder(
        api_key="test",
        base_url="https://example.invalid",
        model="Vietnamese_Embedding",
        timeout_seconds=1,
        provider_label="fpt_embedding",
        expected_dimensions=2,
        sdk_client=_FakeEmbeddingSdk(response),
    )

    vectors = asyncio.run(embedder.embed(["safe text"]))

    assert vectors == [[0.1, 0.2]]
    assert token_metric._value.get() - tokens_before == 40


def test_embedding_content_capture_records_input_output_and_usage_details(
    monkeypatch,
) -> None:
    response = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])],
        usage=SimpleNamespace(prompt_tokens=40, total_tokens=40),
    )
    observation = _CapturedObservation()
    start_kwargs = {}

    @contextmanager
    def fake_observation(name, **kwargs):
        start_kwargs["name"] = name
        start_kwargs.update(kwargs)
        yield observation

    monkeypatch.setattr(embedder_module, "start_observation", fake_observation)
    settings = Settings(
        LANGFUSE_CAPTURE_CONTENT=True,
        _env_file=None,
    )
    embedder = OpenAICompatibleEmbedder(
        api_key="test",
        base_url="https://example.invalid",
        model="Vietnamese_Embedding",
        timeout_seconds=1,
        provider_label="fpt_embedding",
        expected_dimensions=2,
        settings=settings,
        sdk_client=_FakeEmbeddingSdk(response),
    )

    vectors = asyncio.run(embedder.embed(["safe text"]))

    assert vectors == [[0.1, 0.2]]
    assert start_kwargs["name"] == "hera.embedding.provider_call"
    assert start_kwargs["input"] == ["safe text"]
    assert start_kwargs["model"] == "Vietnamese_Embedding"
    usage_update = observation.updates[0]
    assert usage_update["output"] == {
        "batch_size": 1,
        "dimensions": 2,
    }
    assert usage_update["usage_details"] == {
        "input": 40,
        "total": 40,
    }
