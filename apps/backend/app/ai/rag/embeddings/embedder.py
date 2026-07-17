"""Embedding provider interface."""

from __future__ import annotations

from typing import Any, Protocol

from app.core.config import Settings


class Embedder(Protocol):
    """Embedding model contract."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""


class NoopEmbedder:
    """Placeholder embedder used until a provider is configured."""

    provider_name = "noop"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return empty vectors for placeholder use."""

        return [[] for _ in texts]


class OpenAICompatibleEmbedder:
    """Embedding adapter for OpenAI-compatible APIs such as FPT Cloud."""

    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        provider_name: str = "openai-compatible",
        sdk_client: Any | None = None,
    ) -> None:
        self.model = model
        self.provider_name = provider_name
        if sdk_client is not None:
            self._client = sdk_client
            return

        from openai import AsyncOpenAI

        if base_url:
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = AsyncOpenAI(api_key=api_key)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""

        if not texts:
            return []

        response = await self._client.embeddings.create(
            input=texts,
            model=self.model,
        )
        data = sorted(response.data, key=lambda item: getattr(item, "index", 0))
        return [list(item.embedding) for item in data]


def build_embedder(settings: Settings) -> Embedder:
    """Build the configured embedding provider."""

    if settings.EMBEDDING_PROVIDER == "fpt":
        if not settings.OPEN_API_KEY:
            return NoopEmbedder()
        return OpenAICompatibleEmbedder(
            api_key=settings.OPEN_API_KEY,
            base_url=settings.OPEN_API_BASE_URL,
            model=settings.OPEN_API_EMBEDDING_MODEL or settings.EMBEDDING_MODEL,
            provider_name="fpt",
        )

    if settings.EMBEDDING_PROVIDER == "openai":
        if not settings.OPENAI_API_KEY:
            return NoopEmbedder()
        return OpenAICompatibleEmbedder(
            api_key=settings.OPENAI_API_KEY,
            model=settings.EMBEDDING_MODEL,
            provider_name="openai",
        )

    return NoopEmbedder()
