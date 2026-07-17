"""Retrieval service placeholder."""

from __future__ import annotations

from app.ai.rag.schemas import RetrievalRequest, RetrievalResponse


class RetrievalService:
    """Retrieve official hospital knowledge.

    TODO: Connect to the approved hospital knowledge index once source documents
    and metadata rules are available.
    """

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        """Return retrieved chunks. Currently empty until official data exists."""

        return RetrievalResponse(query=request.query, chunks=[])

