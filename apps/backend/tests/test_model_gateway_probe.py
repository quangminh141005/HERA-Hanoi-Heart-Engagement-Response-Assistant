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


def _settings(**overrides) -> Settings:
    values = {
        "API_KEY": "test-key",
        "FPT_LLM_MODEL": "gpt-oss-120b",
        "FPT_EMBEDDING_MODEL": "Vietnamese_Embedding",
        "EMBEDDING_DIMENSIONS": 1024,
        "RATE_LIMIT_ENABLED": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_probe_accepts_both_required_models() -> None:
    llm = FakeLLM()
    result = asyncio.run(
        verify_model_gateway(
            _settings(MODEL_PROBE_LLM_MAX_TOKENS=13),
            llm_client=llm,
            embedder=FakeEmbedder(),
        )
    )

    assert result["status"] == "ok"
    assert result["llm_model"] == "gpt-oss-120b"
    assert result["embedding_model"] == "Vietnamese_Embedding"
    assert result["embedding_dimensions"] == 1024
    assert llm.calls[0]["max_tokens"] == 13


def test_probe_rejects_wrong_live_embedding_dimension() -> None:
    with pytest.raises(ModelGatewayProbeError, match="dimension mismatch"):
        asyncio.run(
            verify_model_gateway(
                _settings(),
                llm_client=FakeLLM(),
                embedder=FakeEmbedder(12),
            )
        )


def test_probe_requires_shared_fpt_key() -> None:
    with pytest.raises(ModelGatewayProbeError, match="API_KEY"):
        asyncio.run(
            verify_model_gateway(
                _settings(API_KEY=None, OPENAI_API_KEY=None),
                llm_client=FakeLLM(),
                embedder=FakeEmbedder(),
            )
        )
