from __future__ import annotations

import asyncio

import pytest
from app.core.config import Settings

from scripts.verify_model_gateway import ModelGatewayProbeError, verify_model_gateway


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate(self, messages, **kwargs):
        del messages
        self.calls.append(kwargs)
        return "HERA is ready"


class FakeEmbedder:
    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions

    async def embed(self, texts):
        del texts
        return [[0.0] * self.dimensions]


class FakeReranker:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def rerank(self, *, query, chunks, top_n):
        self.calls.append({"query": query, "chunks": chunks, "top_n": top_n})
        return chunks[:top_n]


def _settings(**overrides) -> Settings:
    values = {
        "API_KEY": "test-key",
        "FPT_LLM_MODEL": "gpt-oss-120b",
        "FPT_GUARD_MODEL": "gpt-oss-20b",
        "FPT_EMBEDDING_MODEL": "Vietnamese_Embedding",
        "EMBEDDING_DIMENSIONS": 1024,
        "RERANK_MODEL": "bge-reranker-v2-m3",
        "RATE_LIMIT_ENABLED": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_probe_accepts_both_required_models() -> None:
    llm = FakeLLM()
    guard = FakeLLM()
    reranker = FakeReranker()
    result = asyncio.run(
        verify_model_gateway(
            _settings(MODEL_PROBE_LLM_MAX_TOKENS=1024),
            llm_client=llm,
            guard_client=guard,
            embedder=FakeEmbedder(),
            reranker=reranker,
        )
    )

    assert result["status"] == "ok"
    assert result["llm_model"] == "gpt-oss-120b"
    assert result["guard_model"] == "gpt-oss-20b"
    assert result["embedding_model"] == "Vietnamese_Embedding"
    assert result["embedding_dimensions"] == 1024
    assert result["rerank_model"] == "bge-reranker-v2-m3"
    assert llm.calls[0]["max_tokens"] == 1024
    assert guard.calls[0]["max_tokens"] == 1024
    assert reranker.calls[0]["top_n"] == 1


def test_probe_rejects_wrong_live_embedding_dimension() -> None:
    with pytest.raises(ModelGatewayProbeError, match="dimension mismatch"):
        asyncio.run(
            verify_model_gateway(
                _settings(),
                llm_client=FakeLLM(),
                guard_client=FakeLLM(),
                embedder=FakeEmbedder(12),
                reranker=FakeReranker(),
            )
        )


def test_probe_requires_shared_fpt_key() -> None:
    with pytest.raises(ModelGatewayProbeError, match="API_KEY"):
        asyncio.run(
            verify_model_gateway(
                _settings(API_KEY=None, OPENAI_API_KEY=None),
                llm_client=FakeLLM(),
                guard_client=FakeLLM(),
                embedder=FakeEmbedder(),
                reranker=FakeReranker(),
            )
        )
