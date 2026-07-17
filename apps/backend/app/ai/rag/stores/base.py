"""Vector store interfaces."""

from __future__ import annotations

from typing import Protocol

from app.ai.rag.schemas import RetrievedChunk


class VectorStore(Protocol):
    """Vector store contract."""

    async def search(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Return nearest official knowledge chunks."""
