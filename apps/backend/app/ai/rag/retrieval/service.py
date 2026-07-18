"""Approved-fact retrieval for the small HERA knowledge base."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import unicodedata
from collections import OrderedDict
from time import monotonic

from app.ai.observability.tracing import start_observation
from app.ai.rag.embeddings.embedder import Embedder
from app.ai.rag.query_expansion import QueryExpander
from app.ai.rag.rerank import Reranker
from app.ai.rag.schemas import (
    KnowledgeSource,
    RetrievalRequest,
    RetrievalResponse,
    RetrievedChunk,
)
from app.core.config import Settings
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
        reranker: Reranker | None = None,
        rerank_top_n: int = 3,
        query_expander: QueryExpander | None = None,
        settings: Settings | None = None,
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
        self.reranker = reranker
        self.rerank_top_n = rerank_top_n
        self.query_expander = query_expander
        self.settings = settings
        self._query_vector_cache: OrderedDict[
            str,
            tuple[float, list[float]],
        ] = OrderedDict()

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResponse:
        """Return deterministic lexical candidates with source provenance."""

        expanded_query = await self._expand_query(request.query)
        retrieval_queries = [request.query]
        if expanded_query:
            retrieval_queries.append(expanded_query)
        lexical_rows = []
        allowed_intents = set(request.allowed_intents) or None
        for retrieval_query in retrieval_queries:
            lexical_rows.extend(
                await asyncio.to_thread(
                    self.repository.search_facts,
                    query=retrieval_query,
                    allowed_intents=allowed_intents,
                    limit=max(request.top_k * 3, request.top_k),
                )
            )
            if (
                allowed_intents
                and self.settings is not None
                and self.settings.RAG_CROSS_INTENT_RETRIEVAL_ENABLED
            ):
                lexical_rows.extend(
                    await asyncio.to_thread(
                        self.repository.search_facts,
                        query=retrieval_query,
                        allowed_intents=None,
                        limit=max(request.top_k * 3, request.top_k),
                    )
                )
        lexical_ranked: dict[str, RetrievedChunk] = {}
        for row in lexical_rows:
            chunk_id = f"CHUNK-{row['fact_id']}-001"
            lexical_ranked[chunk_id] = RetrievedChunk(
                chunk_id=chunk_id,
                text=row["claim_vi"],
                score=min(1.0, 0.55 + (0.08 * int(row["score"]))),
                source=KnowledgeSource(
                    source_id=row["source_id"],
                    fact_id=row["fact_id"],
                    title=row["title"],
                    url=row["url"],
                    document_type="official_fact",
                ),
            )

        lexical_ordered = _ordered_chunks(lexical_ranked)
        if _has_unique_exact_match(
            request.query,
            lexical_ordered,
            self.exact_lexical_score,
        ):
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

        semantic_ranked: dict[str, RetrievedChunk] = {}
        if self.embedder is not None:
            try:
                semantic_query = (
                    f"{request.query}\n{expanded_query}"
                    if expanded_query
                    else request.query
                )
                query_vector = await self._embed_query(semantic_query)
                semantic_rows = await asyncio.to_thread(
                    self.repository.search_embedded_knowledge_chunks,
                    query_vector=query_vector,
                    allowed_intents=allowed_intents,
                    limit=max(request.top_k * 3, request.top_k),
                    minimum_score=self.minimum_semantic_score,
                )
                if (
                    allowed_intents
                    and self.settings is not None
                    and self.settings.RAG_CROSS_INTENT_RETRIEVAL_ENABLED
                ):
                    semantic_rows.extend(
                        await asyncio.to_thread(
                            self.repository.search_embedded_knowledge_chunks,
                            query_vector=query_vector,
                            allowed_intents=None,
                            limit=max(request.top_k * 3, request.top_k),
                            minimum_score=self.minimum_semantic_score,
                        )
                    )
                for row in semantic_rows:
                    score = float(row["score"])
                    semantic_ranked[row["chunk_id"]] = RetrievedChunk(
                        chunk_id=row["chunk_id"],
                        text=row["content_vi"],
                        score=score * 0.85,
                        source=KnowledgeSource(
                            source_id=row["source_id"],
                            fact_id=row["fact_id"],
                            title=row["title"],
                            url=row["url"],
                            document_type="official_fact_embedding",
                        ),
                    )
            except Exception as exc:
                logger.warning(
                    "semantic retrieval failed; using approved lexical facts",
                    extra={
                        "event": "semantic_retrieval_fallback",
                        "error_type": exc.__class__.__name__,
                    },
                )

        candidate_limit = max(request.top_k * 3, request.top_k)
        ordered = self._fuse_with_trace(
            lexical_ordered,
            _ordered_chunks(semantic_ranked),
            top_k=candidate_limit,
        )
        if self.reranker is not None and len(ordered) > 1:
            chunks = await self.reranker.rerank(
                query=(
                    f"{request.query}\n{expanded_query}"
                    if expanded_query
                    else request.query
                ),
                chunks=ordered[:candidate_limit],
                top_n=min(request.top_k, self.rerank_top_n),
            )
        elif ordered:
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

    async def _expand_query(self, query: str) -> str | None:
        if self.query_expander is None:
            return None
        return await self.query_expander.expand(query)

    def _fuse_with_trace(
        self,
        lexical: list[RetrievedChunk],
        semantic: list[RetrievedChunk],
        *,
        top_k: int,
    ) -> list[RetrievedChunk]:
        if self.settings is None:
            return _rrf_fuse(lexical, semantic, top_k=top_k)

        with start_observation(
            "hera.rag.rrf_fusion",
            settings=self.settings,
            as_type="retriever",
            metadata={
                "algorithm": "reciprocal_rank_fusion",
                "lexical_candidates": len(lexical),
                "semantic_candidates": len(semantic),
                "top_k": top_k,
            },
        ) as observation:
            fused = _rrf_fuse(lexical, semantic, top_k=top_k)
            observation.update(metadata={"fused_candidates": len(fused)})
            return fused

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

        query_vectors = await self._embed_with_trace(query)
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

    async def _embed_with_trace(self, query: str) -> list[list[float]]:
        if self.embedder is None:
            raise ValueError("Embedding provider is not configured")
        if self.settings is None:
            return await self.embedder.embed([query])

        with start_observation(
            "hera.rag.embedding_query",
            settings=self.settings,
            as_type="embedding",
            metadata={
                "provider": self.settings.EMBEDDING_PROVIDER,
                "model": self.embedding_model,
                "expected_dimensions": self.expected_embedding_dimensions,
                "batch_size": 1,
                "content_capture": False,
            },
        ) as observation:
            try:
                vectors = await self.embedder.embed([query])
            except Exception as exc:
                observation.update(
                    metadata={
                        "result": "error",
                        "error_type": exc.__class__.__name__,
                    }
                )
                raise
            observation.update(
                metadata={
                    "result": "success",
                    "dimensions": len(vectors[0]) if vectors and vectors[0] else 0,
                }
            )
            return vectors

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


def _rrf_fuse(
    lexical: list[RetrievedChunk],
    semantic: list[RetrievedChunk],
    *,
    top_k: int,
    rank_constant: int = 60,
) -> list[RetrievedChunk]:
    """Fuse lexical and semantic rankings with Reciprocal Rank Fusion."""

    candidates: dict[str, RetrievedChunk] = {}
    rrf_scores: dict[str, float] = {}
    appearances: dict[str, int] = {}

    for ranking in (lexical, semantic):
        for rank, chunk in enumerate(ranking, start=1):
            candidates.setdefault(chunk.chunk_id, chunk)
            rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0) + (
                1.0 / (rank_constant + rank)
            )
            appearances[chunk.chunk_id] = appearances.get(chunk.chunk_id, 0) + 1
            existing = candidates[chunk.chunk_id]
            if chunk.score > existing.score:
                candidates[chunk.chunk_id] = chunk

    if not candidates:
        return []

    max_rrf = max(rrf_scores.values())
    fused: list[RetrievedChunk] = []
    for chunk_id, chunk in candidates.items():
        normalized_rrf = rrf_scores[chunk_id] / max_rrf if max_rrf else 0.0
        duplicate_boost = 0.04 if appearances[chunk_id] > 1 else 0.0
        fused_score = min(
            1.0,
            max(chunk.score, 0.55 + (0.4 * normalized_rrf)) + duplicate_boost,
        )
        fused.append(chunk.model_copy(update={"score": fused_score}))

    return sorted(
        fused,
        key=lambda chunk: (
            -rrf_scores[chunk.chunk_id],
            -chunk.score,
            chunk.chunk_id,
        ),
    )[:top_k]


def _has_unique_exact_match(
    query: str,
    chunks: list[RetrievedChunk],
    threshold: float,
) -> bool:
    if not chunks or chunks[0].score < threshold:
        return False
    if len(chunks) > 1 and chunks[0].score <= chunks[1].score:
        return False
    return _normalize_exact_text(query) == _normalize_exact_text(chunks[0].text)


def _normalize_exact_text(value: str) -> str:
    """Normalize presentation differences without treating token overlap as exact."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()
