"""Retrieval interfaces."""

from __future__ import annotations

from typing import Protocol

from app.ai.rag.schemas import RetrievalRequest, RetrievalResponse


class Retriever(Protocol):
    """Retriever contract used by the RAG pipeline."""

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        """Return official hospital knowledge chunks."""

