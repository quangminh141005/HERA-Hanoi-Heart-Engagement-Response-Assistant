"""Verify the configured FPT LLM and embedding endpoints with synthetic input."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ai.llm.client import OpenAILLMClient  # noqa: E402
from app.ai.rag.embeddings.embedder import OpenAICompatibleEmbedder  # noqa: E402
from app.ai.rag.rerank import FPTReranker  # noqa: E402
from app.ai.rag.schemas import KnowledgeSource, RetrievedChunk  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402


class ModelGatewayProbeError(RuntimeError):
    """Raised when a deployment model dependency is not usable."""


async def verify_model_gateway(
    settings: Settings,
    *,
    llm_client: Any | None = None,
    guard_client: Any | None = None,
    embedder: Any | None = None,
    reranker: Any | None = None,
) -> dict[str, object]:
    """Call required model endpoints without sending user or hospital data."""

    if not settings.API_KEY:
        raise ModelGatewayProbeError("API_KEY is not configured")
    if settings.FPT_LLM_MODEL != "gpt-oss-120b":
        raise ModelGatewayProbeError("FPT_LLM_MODEL must be gpt-oss-120b")
    if settings.FPT_GUARD_MODEL != "gpt-oss-20b":
        raise ModelGatewayProbeError("FPT_GUARD_MODEL must be gpt-oss-20b")
    if settings.FPT_EMBEDDING_MODEL != "Vietnamese_Embedding":
        raise ModelGatewayProbeError(
            "FPT_EMBEDDING_MODEL must be Vietnamese_Embedding"
        )
    if settings.EMBEDDING_DIMENSIONS != 1024:
        raise ModelGatewayProbeError("EMBEDDING_DIMENSIONS must be 1024")
    if settings.RERANK_ENABLED and settings.RERANK_MODEL != "bge-reranker-v2-m3":
        raise ModelGatewayProbeError("RERANK_MODEL must be bge-reranker-v2-m3")

    active_llm = llm_client or OpenAILLMClient(
        api_key=settings.API_KEY,
        model=settings.FPT_LLM_MODEL,
        base_url=settings.FPT_API_BASE_URL,
        timeout_seconds=settings.MODEL_TIMEOUT_SECONDS,
        provider_label="fpt_llm",
    )
    active_embedder = embedder or OpenAICompatibleEmbedder(
        api_key=settings.API_KEY,
        model=settings.FPT_EMBEDDING_MODEL,
        base_url=settings.EMBEDDING_BASE_URL or settings.FPT_API_BASE_URL,
        timeout_seconds=settings.MODEL_TIMEOUT_SECONDS,
        provider_label="fpt_embedding",
        expected_dimensions=settings.EMBEDDING_DIMENSIONS,
    )
    active_guard = guard_client or OpenAILLMClient(
        api_key=settings.API_KEY,
        model=settings.FPT_GUARD_MODEL,
        base_url=settings.FPT_API_BASE_URL,
        timeout_seconds=settings.MODEL_TIMEOUT_SECONDS,
        provider_label="fpt_guard",
    )
    active_reranker = reranker
    if active_reranker is None and settings.RERANK_ENABLED:
        active_reranker = FPTReranker(
            api_key=settings.API_KEY,
            model=settings.RERANK_MODEL,
            base_url=settings.FPT_API_BASE_URL,
            timeout_seconds=settings.MODEL_TIMEOUT_SECONDS,
        )

    guard_messages = [
        {
            "role": "system",
            "content": (
                "Synthetic routing probe. Return JSON only: "
                '{"emergency":false,"emergency_confidence":0,'
                '"intent":"greeting","intent_confidence":1,"reason":"probe"}'
            ),
        },
        {"role": "user", "content": "Xin chao"},
    ]
    rerank_chunks = [
        _probe_chunk("CHUNK-PROBE-1", "Carson City is the capital of Nevada."),
        _probe_chunk("CHUNK-PROBE-2", "Washington, D.C. is the capital of the United States."),
    ]
    rerank_task = (
        active_reranker.rerank(
            query="capital of the United States",
            chunks=rerank_chunks,
            top_n=1,
        )
        if active_reranker is not None
        else _no_rerank_probe()
    )

    llm_result, guard_result, vectors, rerank_result = await asyncio.gather(
        active_llm.generate(
            [
                {
                    "role": "system",
                    "content": "Synthetic connectivity probe. Reply with OK only.",
                },
                {"role": "user", "content": "OK?"},
            ],
            temperature=0.0,
            max_tokens=settings.MODEL_PROBE_LLM_MAX_TOKENS,
        ),
        active_guard.generate(
            guard_messages,
            temperature=0.0,
            max_tokens=settings.MODEL_PROBE_LLM_MAX_TOKENS,
        ),
        active_embedder.embed(["HERA synthetic deployment connectivity probe"]),
        rerank_task,
        return_exceptions=True,
    )
    if isinstance(llm_result, BaseException):
        detail = str(llm_result).strip()
        raise ModelGatewayProbeError(
            f"LLM probe failed ({llm_result.__class__.__name__})"
            + (f": {detail}" if detail else "")
        ) from llm_result
    if isinstance(guard_result, BaseException):
        detail = str(guard_result).strip()
        raise ModelGatewayProbeError(
            f"Guard probe failed ({guard_result.__class__.__name__})"
            + (f": {detail}" if detail else "")
        ) from guard_result
    if isinstance(vectors, BaseException):
        detail = str(vectors).strip()
        raise ModelGatewayProbeError(
            f"Embedding probe failed ({vectors.__class__.__name__})"
            + (f": {detail}" if detail else "")
        ) from vectors
    if isinstance(rerank_result, BaseException):
        detail = str(rerank_result).strip()
        raise ModelGatewayProbeError(
            f"Rerank probe failed ({rerank_result.__class__.__name__})"
            + (f": {detail}" if detail else "")
        ) from rerank_result
    if not isinstance(llm_result, str) or not llm_result.strip():
        raise ModelGatewayProbeError("The LLM returned no text")
    if not isinstance(guard_result, str) or not guard_result.strip():
        raise ModelGatewayProbeError("The guard model returned no text")
    if len(vectors) != 1 or len(vectors[0]) != settings.EMBEDDING_DIMENSIONS:
        received = len(vectors[0]) if len(vectors) == 1 else 0
        raise ModelGatewayProbeError(
            f"Embedding dimension mismatch: expected 1024, received {received}"
        )
    if not all(isinstance(value, int | float) and math.isfinite(value) for value in vectors[0]):
        raise ModelGatewayProbeError("Embedding contains a non-finite value")
    if settings.RERANK_ENABLED and (
        not isinstance(rerank_result, list)
        or not rerank_result
        or not isinstance(rerank_result[0], RetrievedChunk)
    ):
        raise ModelGatewayProbeError("Rerank returned no ranked document")

    return {
        "status": "ok",
        "llm_model": settings.FPT_LLM_MODEL,
        "guard_model": settings.FPT_GUARD_MODEL,
        "embedding_model": settings.FPT_EMBEDDING_MODEL,
        "embedding_dimensions": len(vectors[0]),
        "rerank_model": settings.RERANK_MODEL if settings.RERANK_ENABLED else None,
        "synthetic_input_only": True,
    }


async def _no_rerank_probe() -> list[RetrievedChunk]:
    return []


def _probe_chunk(chunk_id: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        score=0.5,
        source=KnowledgeSource(
            source_id="SRC-PROBE",
            title="Synthetic probe",
            url=None,
            document_type="synthetic_probe",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = asyncio.run(verify_model_gateway(get_settings()))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": exc.__class__.__name__,
                    "detail": (
                        str(exc)
                        if isinstance(exc, ModelGatewayProbeError)
                        else "Model gateway request failed; inspect provider access and egress."
                    ),
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
