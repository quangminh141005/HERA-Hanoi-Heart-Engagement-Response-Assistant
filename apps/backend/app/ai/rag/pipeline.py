"""RAG orchestration for official hospital knowledge."""

from __future__ import annotations

from app.ai.rag.generation.service import GenerationService
from app.ai.rag.retrieval.service import RetrievalService
from app.ai.rag.schemas import GroundedAnswer, RetrievalRequest


class RAGPipeline:
    """Retrieve context and generate a grounded answer."""

    def __init__(
        self,
        retrieval_service: RetrievalService,
        generation_service: GenerationService,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.generation_service = generation_service

    async def answer(
        self,
        query: str,
        *,
        locale: str = "vi",
        top_k: int = 5,
        allowed_intents: set[str] | None = None,
    ) -> GroundedAnswer:
        """Run retrieval and grounded generation."""

        retrieval = await self.retrieval_service.retrieve(
            RetrievalRequest(
                query=query,
                locale=locale,
                top_k=top_k,
                allowed_intents=sorted(allowed_intents or set()),
            )
        )
        return await self.generation_service.generate(
            query,
            retrieval.chunks,
            locale=locale,
        )

