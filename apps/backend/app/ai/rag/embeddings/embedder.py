"""Embedding provider interface."""

from __future__ import annotations

from typing import Any, Protocol

from app.core.config import Settings
from app.observability.prometheus import record_upstream_failure


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
        sdk_client: Any | None = None,
    ) -> None:
        self.model = model
        self.provider_label = provider_label
        self.expected_dimensions = expected_dimensions
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
        try:
            response = await self._client.embeddings.create(
                model=self.model,
                input=texts,
            )
        except Exception as exc:
            record_upstream_failure(self.provider_label, exc)
            raise
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
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
    )

