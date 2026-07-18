"""Hybrid retrieval tests for Vietnamese_Embedding with safe fallback."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from app.ai.rag.retrieval.service import RetrievalService
from app.ai.rag.schemas import RetrievalRequest


class StaticRepository:
    def __init__(self, *, lexical=None, semantic=None):
        self.lexical = lexical or []
        self.semantic = semantic or []
        self.semantic_reads = 0

    def search_facts(self, *, query: str, limit: int, allowed_intents=None):
        del query, limit, allowed_intents
        return self.lexical

    def search_embedded_knowledge_chunks(
        self,
        *,
        query_vector,
        allowed_intents,
        limit,
        minimum_score,
    ):
        del query_vector, allowed_intents, limit, minimum_score
        self.semantic_reads += 1
        return self.semantic


class StaticEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[1.0, 0.0] for _ in texts]


class FailingEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        del texts
        raise RuntimeError("provider unavailable")


class SharedCache:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], object] = {}

    @staticmethod
    def _key(namespace: str, identity: Mapping[str, object]) -> tuple[str, str]:
        return namespace, repr(sorted(identity.items()))

    def get(self, namespace: str, identity: Mapping[str, object]):
        return self.values.get(self._key(namespace, identity))

    def set(
        self,
        namespace: str,
        identity: Mapping[str, object],
        value: object,
    ) -> None:
        self.values[self._key(namespace, identity)] = value

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None


def test_semantic_retrieval_uses_approved_embedded_fact() -> None:
    repository = StaticRepository(
        semantic=[
            {
                "chunk_id": "CHUNK-FACT-1-001",
                "fact_id": "FACT-1",
                "source_id": "SRC-1",
                "content_vi": "Bệnh viện tiếp nhận đặt lịch qua điện thoại.",
                "title": "Nguồn chính thức",
                "url": "https://example.test/official",
                "score": 0.9,
            }
        ]
    )
    service = RetrievalService(
        repository,
        embedder=StaticEmbedder(),
        minimum_semantic_score=0.55,
    )

    response = asyncio.run(
        service.retrieve(RetrievalRequest(query="Tôi muốn hẹn khám", top_k=3))
    )

    assert [chunk.chunk_id for chunk in response.chunks] == ["CHUNK-FACT-1-001"]
    assert response.chunks[0].source.document_type == "official_fact_embedding"


def test_embedding_failure_falls_back_to_lexical_fact() -> None:
    lexical = [
        {
            "fact_id": "FACT-1",
            "claim_vi": "Hotline hỗ trợ là 19001082.",
            "score": 2,
            "source_id": "SRC-1",
            "title": "Nguồn chính thức",
            "url": None,
        }
    ]
    semantic = [
        {
            "chunk_id": "CHUNK-FACT-1-001",
            "score": 0.9,
        }
    ]
    service = RetrievalService(
        StaticRepository(lexical=lexical, semantic=semantic),
        embedder=FailingEmbedder(),
    )

    response = asyncio.run(
        service.retrieve(RetrievalRequest(query="hotline", top_k=3))
    )

    assert [chunk.chunk_id for chunk in response.chunks] == ["CHUNK-FACT-1-001"]
    assert response.chunks[0].text == "Hotline hỗ trợ là 19001082."


def test_unique_exact_lexical_fact_skips_embedding_and_marks_fast_path() -> None:
    repository = StaticRepository(
        lexical=[
            {
                "fact_id": "FACT-EXACT",
                "claim_vi": "Người bệnh nên có mặt trước giờ khám 15 phút.",
                "score": 3,
                "source_id": "SRC-1",
                "title": "Nguồn chính thức",
                "url": None,
            }
        ],
        semantic=[{"would": "fail if accessed"}],
    )
    embedder = StaticEmbedder()
    service = RetrievalService(repository, embedder=embedder)

    response = asyncio.run(
        service.retrieve(RetrievalRequest(query="đến sớm bao lâu", top_k=3))
    )

    assert response.chunks[0].source.document_type == "official_fact_exact"
    assert repository.semantic_reads == 0
    assert embedder.calls == 0


def test_query_vector_cache_is_shared_across_replicas() -> None:
    repository = StaticRepository()
    cache = SharedCache()
    first_embedder = StaticEmbedder()
    second_embedder = StaticEmbedder()
    first = RetrievalService(
        repository,
        embedder=first_embedder,
        shared_cache=cache,
        expected_embedding_dimensions=2,
    )
    second = RetrievalService(
        repository,
        embedder=second_embedder,
        shared_cache=cache,
        expected_embedding_dimensions=2,
    )

    async def scenario() -> None:
        await first._embed_query("shared query")
        await second._embed_query("shared query")

    asyncio.run(scenario())

    assert first_embedder.calls == 1
    assert second_embedder.calls == 0


def test_query_vector_is_cached_while_pgvector_search_stays_fresh() -> None:
    repository = StaticRepository(
        semantic=[
            {
                "chunk_id": "CHUNK-FACT-1-001",
                "fact_id": "FACT-1",
                "source_id": "SRC-1",
                "content_vi": "Kênh hỗ trợ chính thức.",
                "title": "Nguồn chính thức",
                "url": None,
                "score": 0.9,
            }
        ]
    )
    embedder = StaticEmbedder()
    service = RetrievalService(repository, embedder=embedder)
    request = RetrievalRequest(query="cùng một câu hỏi", top_k=3)

    async def scenario() -> None:
        await service.retrieve(request)
        await service.retrieve(request)

    asyncio.run(scenario())

    assert repository.semantic_reads == 2
    assert embedder.calls == 1
    assert "cùng một câu hỏi" not in repr(service._query_vector_cache)
