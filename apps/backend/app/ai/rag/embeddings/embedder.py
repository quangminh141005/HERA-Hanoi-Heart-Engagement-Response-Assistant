"""Embedding provider interface."""

from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    """Embedding model contract."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""


class NoopEmbedder:
    """Placeholder embedder used until a provider is configured."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return empty vectors for placeholder use."""

        return [[] for _ in texts]

