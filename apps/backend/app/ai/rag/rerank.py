"""Reranking adapter for approved RAG chunks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Protocol

import httpx

from app.ai.observability.tracing import start_observation
from app.ai.providers.retry import retry_provider_call
from app.ai.rag.schemas import RetrievedChunk
from app.core.config import Settings
from app.observability.prometheus import record_upstream_failure

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    """Rerank retrieved chunks without changing their factual content."""

    async def rerank(
        self,
        *,
        query: str,
        chunks: list[RetrievedChunk],
        top_n: int,
    ) -> list[RetrievedChunk]:
        """Return the most relevant chunks in provider-ranked order."""


class NoopReranker:
    """Fallback reranker that preserves the existing retrieval order."""

    async def rerank(
        self,
        *,
        query: str,
        chunks: list[RetrievedChunk],
        top_n: int,
    ) -> list[RetrievedChunk]:
        del query
        return chunks[:top_n]

    async def close(self) -> None:
        return None


class FPTReranker:
    """FPT-compatible reranker using the custom /v1/rerank endpoint."""

    provider_name = "fpt_rerank"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        settings: Settings | None = None,
        max_concurrent_requests: int = 4,
        cache_enabled: bool = True,
        cache_ttl_seconds: int = 300,
        cache_max_entries: int = 512,
        retry_max_attempts: int = 1,
        retry_base_delay_seconds: float = 0.25,
        retry_max_delay_seconds: float = 2.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.settings = settings
        self.retry_max_attempts = retry_max_attempts
        self.retry_base_delay_seconds = retry_base_delay_seconds
        self.retry_max_delay_seconds = retry_max_delay_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent_requests)
        self._cache_enabled = cache_enabled
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache_max_entries = cache_max_entries
        self._cache: OrderedDict[str, tuple[float, list[int], dict[int, float]]] = (
            OrderedDict()
        )
        self._in_flight: dict[str, asyncio.Task[list[RetrievedChunk]]] = {}
        self._lock = asyncio.Lock()
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def rerank(
        self,
        *,
        query: str,
        chunks: list[RetrievedChunk],
        top_n: int,
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        requested_top_n = max(1, min(top_n, len(chunks)))
        cache_key = _cache_key(query=query, chunks=chunks, top_n=requested_top_n)
        if self._cache_enabled:
            cached = await self._get_cached(cache_key, chunks, requested_top_n)
            if cached is not None:
                return cached

        async with self._lock:
            existing = self._in_flight.get(cache_key)
            if existing is None:
                existing = asyncio.create_task(
                    self._rerank_uncached(
                        query=query,
                        chunks=chunks,
                        top_n=requested_top_n,
                    )
                )
                self._in_flight[cache_key] = existing

        try:
            ranked = await asyncio.shield(existing)
        finally:
            async with self._lock:
                if self._in_flight.get(cache_key) is existing and existing.done():
                    self._in_flight.pop(cache_key, None)

        if self._cache_enabled:
            await self._set_cached(cache_key, chunks, ranked)
        return ranked

    async def _rerank_uncached(
        self,
        *,
        query: str,
        chunks: list[RetrievedChunk],
        top_n: int,
    ) -> list[RetrievedChunk]:
        metadata = {
            "provider": self.provider_name,
            "model": self.model,
            "candidate_count": len(chunks),
            "top_n": top_n,
            "content_capture": bool(
                self.settings and self.settings.LANGFUSE_CAPTURE_CONTENT
            ),
        }
        if self.settings is None:
            return await self._rerank_provider(
                query=query,
                chunks=chunks,
                top_n=top_n,
            )

        trace_kwargs = {}
        if self.settings.LANGFUSE_CAPTURE_CONTENT:
            trace_kwargs["input"] = {
                "query": query,
                "documents": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "score": round(chunk.score, 4),
                        "source_id": chunk.source.source_id,
                        "document_type": chunk.source.document_type,
                        "text": chunk.text,
                    }
                    for chunk in chunks
                ],
                "top_n": top_n,
            }
        with start_observation(
            "hera.rag.rerank",
            settings=self.settings,
            as_type="retriever",
            metadata=metadata,
            **trace_kwargs,
        ) as observation:
            try:
                ranked = await self._rerank_provider(
                    query=query,
                    chunks=chunks,
                    top_n=top_n,
                )
            except Exception as exc:
                observation.update(
                    metadata={
                        **metadata,
                        "result": "fallback",
                        "error_type": exc.__class__.__name__,
                    }
                )
                record_upstream_failure(self.provider_name, exc)
                logger.warning(
                    "rerank provider failed; preserving RRF order",
                    extra={
                        "event": "rerank_provider_failed",
                        "error_type": exc.__class__.__name__,
                    },
                )
                return chunks[:top_n]
            trace_update = {"metadata": {**metadata, "result": "success"}}
            if self.settings.LANGFUSE_CAPTURE_CONTENT:
                trace_update["output"] = {
                    "ranked_documents": [
                        {
                            "chunk_id": chunk.chunk_id,
                            "score": round(chunk.score, 4),
                            "source_id": chunk.source.source_id,
                            "document_type": chunk.source.document_type,
                            "text": chunk.text,
                        }
                        for chunk in ranked
                    ]
                }
            observation.update(**trace_update)
            return ranked

    async def _rerank_provider(
        self,
        *,
        query: str,
        chunks: list[RetrievedChunk],
        top_n: int,
    ) -> list[RetrievedChunk]:
        async with self._semaphore:
            response = await retry_provider_call(
                lambda: self._client.post(
                    f"{self.base_url}/v1/rerank",
                    json={
                        "model": self.model,
                        "query": query,
                        "documents": [chunk.text for chunk in chunks],
                        "top_n": top_n,
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                ),
                label=self.provider_name,
                max_attempts=self.retry_max_attempts,
                base_delay_seconds=self.retry_base_delay_seconds,
                max_delay_seconds=self.retry_max_delay_seconds,
                retry_timeouts=True,
            )
        response.raise_for_status()
        return _apply_rerank_payload(chunks, response.json(), top_n=top_n)

    async def _get_cached(
        self,
        cache_key: str,
        chunks: list[RetrievedChunk],
        top_n: int,
    ) -> list[RetrievedChunk] | None:
        now = time.monotonic()
        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached is None:
                return None
            expires_at, indexes, scores = cached
            if expires_at <= now:
                self._cache.pop(cache_key, None)
                return None
            self._cache.move_to_end(cache_key)
        ranked: list[RetrievedChunk] = []
        for index in indexes[:top_n]:
            if index < 0 or index >= len(chunks):
                return None
            chunk = chunks[index]
            score = scores.get(index)
            if score is not None:
                chunk = chunk.model_copy(update={"score": max(chunk.score, score)})
            ranked.append(chunk)
        return ranked

    async def _set_cached(
        self,
        cache_key: str,
        chunks: list[RetrievedChunk],
        ranked: list[RetrievedChunk],
    ) -> None:
        index_by_id = {chunk.chunk_id: index for index, chunk in enumerate(chunks)}
        indexes: list[int] = []
        scores: dict[int, float] = {}
        for chunk in ranked:
            index = index_by_id.get(chunk.chunk_id)
            if index is None:
                return
            indexes.append(index)
            scores[index] = chunk.score
        async with self._lock:
            self._cache[cache_key] = (
                time.monotonic() + self._cache_ttl_seconds,
                indexes,
                scores,
            )
            self._cache.move_to_end(cache_key)
            while len(self._cache) > self._cache_max_entries:
                self._cache.popitem(last=False)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def build_reranker(settings: Settings) -> Reranker:
    """Build the configured reranker or a no-op fallback."""

    if not settings.RERANK_ENABLED:
        return NoopReranker()
    api_key = settings.API_KEY or settings.OPENAI_API_KEY
    if not api_key or not settings.RERANK_MODEL:
        return NoopReranker()
    return FPTReranker(
        api_key=api_key,
        base_url=settings.FPT_API_BASE_URL,
        model=settings.RERANK_MODEL,
        timeout_seconds=settings.RERANK_TIMEOUT_SECONDS,
        settings=settings,
        max_concurrent_requests=settings.RERANK_MAX_CONCURRENT_REQUESTS,
        cache_enabled=settings.RERANK_CACHE_ENABLED,
        cache_ttl_seconds=settings.RERANK_CACHE_TTL_SECONDS,
        cache_max_entries=settings.RERANK_CACHE_MAX_ENTRIES,
        retry_max_attempts=settings.AI_PROVIDER_RETRY_MAX_ATTEMPTS,
        retry_base_delay_seconds=settings.AI_PROVIDER_RETRY_BASE_DELAY_SECONDS,
        retry_max_delay_seconds=settings.AI_PROVIDER_RETRY_MAX_DELAY_SECONDS,
    )


def _apply_rerank_payload(
    chunks: list[RetrievedChunk],
    payload: Any,
    *,
    top_n: int,
) -> list[RetrievedChunk]:
    results = _extract_results(payload)
    ranked: list[RetrievedChunk] = []
    seen: set[int] = set()
    for item in results:
        index = _coerce_index(item)
        if index is None or index in seen or index < 0 or index >= len(chunks):
            continue
        seen.add(index)
        score = _coerce_score(item)
        chunk = chunks[index]
        if score is not None:
            chunk = chunk.model_copy(update={"score": max(chunk.score, score)})
        ranked.append(chunk)
        if len(ranked) >= top_n:
            break

    if not ranked:
        return chunks[:top_n]
    for index, chunk in enumerate(chunks):
        if len(ranked) >= top_n:
            break
        if index not in seen:
            ranked.append(chunk)
    return ranked[:top_n]


def _cache_key(
    *,
    query: str,
    chunks: list[RetrievedChunk],
    top_n: int,
) -> str:
    payload = {
        "query": query,
        "top_n": top_n,
        "chunks": [
            {
                "id": chunk.chunk_id,
                "text_sha256": hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
            }
            for chunk in chunks
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _extract_results(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("results", "data", "rankings"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _coerce_index(item: Any) -> int | None:
    if not isinstance(item, dict):
        return None
    for key in ("index", "document_index", "doc_index"):
        if key in item:
            try:
                return int(item[key])
            except (TypeError, ValueError):
                return None
    document = item.get("document")
    if isinstance(document, dict) and "index" in document:
        try:
            return int(document["index"])
        except (TypeError, ValueError):
            return None
    return None


def _coerce_score(item: Any) -> float | None:
    if not isinstance(item, dict):
        return None
    for key in ("relevance_score", "score"):
        if key in item:
            try:
                return max(0.0, min(1.0, float(item[key])))
            except (TypeError, ValueError):
                return None
    return None
