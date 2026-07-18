"""Embedding provider interface."""

from __future__ import annotations

from typing import Any, Protocol

from app.ai.observability.tracing import start_observation
from app.ai.providers.retry import retry_provider_call
from app.core.config import Settings
from app.observability.ai_usage import extract_openai_embedding_usage
from app.observability.prometheus import record_ai_usage, record_upstream_failure


class Embedder(Protocol):
    """Embedding model contract."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""


class NoopEmbedder:
    """Safe local fallback that disables semantic retrieval."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return empty vectors so retrieval stays lexical and deterministic."""

        return [[] for _ in texts]


    async def close(self) -> None:
        return None


class OpenAICompatibleEmbedder:
    """Embedding adapter for FPT/OpenAI-compatible endpoints."""

    provider_name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        provider_label: str = "fpt_embedding",
        expected_dimensions: int | None = None,
        retry_max_attempts: int = 1,
        retry_base_delay_seconds: float = 0.25,
        retry_max_delay_seconds: float = 2.0,
        settings: Settings | None = None,
        sdk_client: Any | None = None,
    ) -> None:
        self.model = model
        self.provider_label = provider_label
        self.expected_dimensions = expected_dimensions
        self.settings = settings
        self.retry_max_attempts = retry_max_attempts
        self.retry_base_delay_seconds = retry_base_delay_seconds
        self.retry_max_delay_seconds = retry_max_delay_seconds
        if sdk_client is not None:
            self._client = sdk_client
            return
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.settings is None:
            return await self._embed_provider(texts, observation=None)

        trace_kwargs = {
            "model": self.model,
            "model_parameters": {
                "batch_size": len(texts),
                "expected_dimensions": self.expected_dimensions,
            },
        }
        if self.settings.LANGFUSE_CAPTURE_CONTENT:
            trace_kwargs["input"] = texts
        with start_observation(
            "hera.embedding.provider_call",
            settings=self.settings,
            as_type="embedding",
            metadata={
                "provider": self.provider_label,
                "model": self.model,
                "batch_size": len(texts),
                "expected_dimensions": self.expected_dimensions,
                "content_capture": self.settings.LANGFUSE_CAPTURE_CONTENT,
            },
            **trace_kwargs,
        ) as observation:
            try:
                vectors = await self._embed_provider(texts, observation=observation)
            except Exception as exc:
                observation.update(
                    metadata={
                        "result": "error",
                        "error_type": exc.__class__.__name__,
                    }
                )
                raise
            observation.update(metadata={"result": "success"})
            return vectors

    async def _embed_provider(
        self,
        texts: list[str],
        *,
        observation: Any | None,
    ) -> list[list[float]]:
        try:
            response = await retry_provider_call(
                lambda: self._client.embeddings.create(
                    model=self.model,
                    input=texts,
                ),
                label=self.provider_label,
                max_attempts=self.retry_max_attempts,
                base_delay_seconds=self.retry_base_delay_seconds,
                max_delay_seconds=self.retry_max_delay_seconds,
                retry_timeouts=True,
            )
        except Exception as exc:
            record_upstream_failure(self.provider_label, exc)
            raise
        usage = extract_openai_embedding_usage(response)
        record_ai_usage(
            self.provider_label,
            input_tokens=usage.input_tokens,
            output_tokens=0,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        if observation is not None:
            trace_update = {
                "metadata": {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": 0,
                },
                "usage_details": _langfuse_embedding_usage_details(usage.input_tokens),
            }
            if self.settings is not None and self.settings.LANGFUSE_CAPTURE_CONTENT:
                trace_update["output"] = {
                    "batch_size": len(vectors),
                    "dimensions": len(vectors[0]) if vectors and vectors[0] else 0,
                }
            observation.update(**trace_update)
        if self.expected_dimensions is not None and any(
            len(vector) != self.expected_dimensions for vector in vectors
        ):
            error = RuntimeError("Embedding provider returned an invalid dimension.")
            record_upstream_failure(self.provider_label, error)
            raise error
        return vectors

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result


def build_embedder(settings: Settings) -> Embedder:
    """Build Vietnamese_Embedding only when the shared FPT key is available."""

    if settings.EMBEDDING_PROVIDER == "noop":
        return NoopEmbedder()
    api_key = settings.API_KEY or settings.OPENAI_API_KEY
    model = settings.FPT_EMBEDDING_MODEL or settings.EMBEDDING_MODEL
    base_url = settings.EMBEDDING_BASE_URL or settings.FPT_API_BASE_URL
    if not api_key or not model:
        return NoopEmbedder()
    return OpenAICompatibleEmbedder(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=settings.EMBEDDING_TIMEOUT_SECONDS,
        provider_label="fpt_embedding",
        expected_dimensions=settings.EMBEDDING_DIMENSIONS,
        retry_max_attempts=settings.AI_PROVIDER_RETRY_MAX_ATTEMPTS,
        retry_base_delay_seconds=settings.AI_PROVIDER_RETRY_BASE_DELAY_SECONDS,
        retry_max_delay_seconds=settings.AI_PROVIDER_RETRY_MAX_DELAY_SECONDS,
        settings=settings,
    )


def _langfuse_embedding_usage_details(input_tokens: int) -> dict[str, int]:
    if input_tokens <= 0:
        return {}
    return {
        "input": input_tokens,
        "total": input_tokens,
    }
