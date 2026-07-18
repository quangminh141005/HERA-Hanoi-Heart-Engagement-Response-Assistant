"""Approved-fact retrieval for the small HERA knowledge base."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict
from time import monotonic

from app.ai.rag.embeddings.embedder import Embedder
from app.ai.rag.schemas import (
    KnowledgeSource,
    RetrievalRequest,
    RetrievalResponse,
    RetrievedChunk,
)
from app.structured.cache import StructuredQueryCache
from app.structured.postgres_repository import StructuredReadRepository

logger = logging.getLogger(__name__)


class RetrievalService:
    """Retrieve only approved facts from the structured bundle."""

    def __init__(
        self,
        repository: StructuredReadRepository,
        *,
        embedder: Embedder | None = None,
        minimum_semantic_score: float = 0.55,
        exact_lexical_score: float = 0.79,
        embedding_cache_ttl_seconds: int = 300,
        embedding_cache_size: int = 256,
        shared_cache: StructuredQueryCache | None = None,
        embedding_model: str = "Vietnamese_Embedding",
        expected_embedding_dimensions: int | None = None,
    ):
        self.repository = repository
        self.embedder = embedder
        self.minimum_semantic_score = minimum_semantic_score
        self.exact_lexical_score = exact_lexical_score
        self.embedding_cache_ttl_seconds = embedding_cache_ttl_seconds
        self.embedding_cache_size = embedding_cache_size
        self.shared_cache = shared_cache
        self.embedding_model = embedding_model
        self.expected_embedding_dimensions = expected_embedding_dimensions
        self._query_vector_cache: OrderedDict[
            str,
            tuple[float, list[float]],
        ] = OrderedDict()

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        """Return deterministic lexical candidates with source provenance."""

        lexical_rows = await asyncio.to_thread(
            self.repository.search_facts,
            query=request.query,
            allowed_intents=set(request.allowed_intents) or None,
            limit=max(request.top_k * 3, request.top_k),
        )
        ranked: dict[str, RetrievedChunk] = {}
        for row in lexical_rows:
            chunk_id = f"CHUNK-{row['fact_id']}-001"
            ranked[chunk_id] = RetrievedChunk(
                chunk_id=chunk_id,
                text=row["claim_vi"],
                score=min(1.0, 0.55 + (0.08 * int(row["score"]))),
                source=KnowledgeSource(
                    source_id=row["source_id"],
                    title=row["title"],
                    url=row["url"],
                    document_type="official_fact",
                ),
            )

        lexical_ordered = _ordered_chunks(ranked)
        if _has_unique_exact_match(lexical_ordered, self.exact_lexical_score):
            exact = lexical_ordered[0]
            return RetrievalResponse(
                query=request.query,
                chunks=[
                    exact.model_copy(
                        update={
                            "source": exact.source.model_copy(
                                update={"document_type": "official_fact_exact"}
                            )
                        }
                    )
                ],
            )

        if self.embedder is not None:
            try:
                query_vector = await self._embed_query(request.query)
                semantic_rows = await asyncio.to_thread(
                    self.repository.search_embedded_knowledge_chunks,
                    query_vector=query_vector,
                    allowed_intents=set(request.allowed_intents) or None,
                    limit=max(request.top_k * 3, request.top_k),
                    minimum_score=self.minimum_semantic_score,
                )
                for row in semantic_rows:
                    score = float(row["score"])
                    semantic_chunk = RetrievedChunk(
                        chunk_id=row["chunk_id"],
                        text=row["content_vi"],
                        score=score * 0.85,
                        source=KnowledgeSource(
                            source_id=row["source_id"],
                            title=row["title"],
                            url=row["url"],
                            document_type="official_fact_embedding",
                        ),
                    )
                    existing = ranked.get(row["chunk_id"])
                    if existing is not None:
                        ranked[row["chunk_id"]] = existing.model_copy(
                            update={
                                "score": min(
                                    1.0,
                                    max(existing.score, semantic_chunk.score) + 0.08,
                                )
                            }
                        )
                    else:
                        ranked[row["chunk_id"]] = semantic_chunk
            except Exception as exc:
                logger.warning(
                    "semantic retrieval failed; using approved lexical facts",
                    extra={
                        "event": "semantic_retrieval_fallback",
                        "error_type": exc.__class__.__name__,
                    },
                )

        ordered = _ordered_chunks(ranked)
        if ordered:
            relevance_floor = max(
                self.minimum_semantic_score,
                ordered[0].score - 0.08,
            )
            chunks = [
                chunk for chunk in ordered if chunk.score >= relevance_floor
            ][: request.top_k]
        else:
            chunks = []
        return RetrievalResponse(query=request.query, chunks=chunks)

    async def _embed_query(self, query: str) -> list[float]:
        if self.embedder is None:
            raise ValueError("Embedding provider is not configured")
        cache_key = hashlib.sha256(query.encode("utf-8")).hexdigest()
        now = monotonic()
        cached = self._query_vector_cache.get(cache_key)
        if cached is not None and cached[0] > now:
            self._query_vector_cache.move_to_end(cache_key)
            return cached[1]

        shared_identity = {
            "query": query,
            "model": self.embedding_model,
            "dimensions": self.expected_embedding_dimensions,
        }
        if self.shared_cache is not None:
            shared = await asyncio.to_thread(
                self.shared_cache.get,
                "embedding-query",
                shared_identity,
            )
            shared_vector = _validated_cached_vector(
                shared,
                expected_dimensions=self.expected_embedding_dimensions,
            )
            if shared_vector is not None:
                self._remember_query_vector(cache_key, shared_vector, now=now)
                return shared_vector

        query_vectors = await self.embedder.embed([query])
        if len(query_vectors) != 1 or not query_vectors[0]:
            raise ValueError("Embedding provider returned no query vector")
        query_vector = [float(value) for value in query_vectors[0]]
        if (
            self.expected_embedding_dimensions is not None
            and len(query_vector) != self.expected_embedding_dimensions
        ):
            raise ValueError("Embedding provider returned an invalid dimension")
        if self.shared_cache is not None:
            await asyncio.to_thread(
                self.shared_cache.set,
                "embedding-query",
                shared_identity,
                {"vector": query_vector},
            )
        self._remember_query_vector(cache_key, query_vector, now=now)
        return query_vector

    def _remember_query_vector(
        self,
        cache_key: str,
        query_vector: list[float],
        *,
        now: float,
    ) -> None:
        self._query_vector_cache[cache_key] = (
            now + self.embedding_cache_ttl_seconds,
            query_vector,
        )
        self._query_vector_cache.move_to_end(cache_key)
        while len(self._query_vector_cache) > self.embedding_cache_size:
            self._query_vector_cache.popitem(last=False)


def _validated_cached_vector(
    payload: object,
    *,
    expected_dimensions: int | None,
) -> list[float] | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("vector"), list):
        return None
    try:
        vector = [float(value) for value in payload["vector"]]
    except (TypeError, ValueError):
        return None
    if not vector:
        return None
    if expected_dimensions is not None and len(vector) != expected_dimensions:
        return None
    return vector


def _ordered_chunks(ranked: dict[str, RetrievedChunk]) -> list[RetrievedChunk]:
    return sorted(
        ranked.values(),
        key=lambda chunk: (-chunk.score, chunk.chunk_id),
    )


def _has_unique_exact_match(
    chunks: list[RetrievedChunk],
    threshold: float,
) -> bool:
    if not chunks or chunks[0].score < threshold:
        return False
    return len(chunks) == 1 or chunks[0].score > chunks[1].score

