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
from app.core.config import Settings, get_settings  # noqa: E402


class ModelGatewayProbeError(RuntimeError):
    """Raised when a deployment model dependency is not usable."""


async def verify_model_gateway(
    settings: Settings,
    *,
    llm_client: Any | None = None,
    embedder: Any | None = None,
) -> dict[str, object]:
    """Call both required models without sending user or hospital data."""

    if not settings.API_KEY:
        raise ModelGatewayProbeError("API_KEY is not configured")
    if settings.FPT_LLM_MODEL != "gpt-oss-20b":
        raise ModelGatewayProbeError("FPT_LLM_MODEL must be gpt-oss-20b")
    if settings.FPT_EMBEDDING_MODEL != "Vietnamese_Embedding":
        raise ModelGatewayProbeError(
            "FPT_EMBEDDING_MODEL must be Vietnamese_Embedding"
        )
    if settings.EMBEDDING_DIMENSIONS != 1024:
        raise ModelGatewayProbeError("EMBEDDING_DIMENSIONS must be 1024")

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

    llm_result, vectors = await asyncio.gather(
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
        active_embedder.embed(["HERA synthetic deployment connectivity probe"]),
        return_exceptions=True,
    )
    if isinstance(llm_result, BaseException):
        detail = str(llm_result).strip()
        raise ModelGatewayProbeError(
            f"LLM probe failed ({llm_result.__class__.__name__})"
            + (f": {detail}" if detail else "")
        ) from llm_result
    if isinstance(vectors, BaseException):
        detail = str(vectors).strip()
        raise ModelGatewayProbeError(
            f"Embedding probe failed ({vectors.__class__.__name__})"
            + (f": {detail}" if detail else "")
        ) from vectors
    if not isinstance(llm_result, str) or not llm_result.strip():
        raise ModelGatewayProbeError("The LLM returned no text")
    if len(vectors) != 1 or len(vectors[0]) != settings.EMBEDDING_DIMENSIONS:
        received = len(vectors[0]) if len(vectors) == 1 else 0
        raise ModelGatewayProbeError(
            f"Embedding dimension mismatch: expected 1024, received {received}"
        )
    if not all(isinstance(value, int | float) and math.isfinite(value) for value in vectors[0]):
        raise ModelGatewayProbeError("Embedding contains a non-finite value")

    return {
        "status": "ok",
        "llm_model": settings.FPT_LLM_MODEL,
        "embedding_model": settings.FPT_EMBEDDING_MODEL,
        "embedding_dimensions": len(vectors[0]),
        "synthetic_input_only": True,
    }


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
