"""pgvector store placeholder."""

from __future__ import annotations

from app.ai.rag.schemas import RetrievedChunk


class PgVectorKnowledgeStore:
    """PostgreSQL/pgvector adapter placeholder.

    TODO: implement once the official knowledge chunk schema is designed.
    """

    def __init__(self, database_url: str, collection: str):
        self.database_url = database_url
        self.collection = collection

    async def search(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        """Return vector search results when schema exists."""

        del query_embedding, top_k
        return []
