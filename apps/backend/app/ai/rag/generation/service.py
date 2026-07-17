"""Grounded answer generation service."""

from __future__ import annotations

from app.ai.llm.client import LLMClient
from app.ai.rag.schemas import GroundedAnswer, RetrievedChunk


class GenerationService:
    """Generate grounded answers from retrieved chunks."""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        locale: str = "vi",
    ) -> GroundedAnswer:
        """Generate an answer. Refuse when no official context is available."""

        if not chunks:
            return GroundedAnswer(
                answer=(
                    "Hiện tại HERA chưa có đủ nguồn chính thức để trả lời chắc chắn "
                    "câu hỏi này. Vui lòng kiểm tra website chính thức của Bệnh viện "
                    "Tim Hà Nội hoặc liên hệ hotline bệnh viện để được xác nhận."
                ),
                citations=[],
                confidence=0.0,
            )

        context = "\n\n".join(
            f"[{chunk.source.source_id}] {chunk.text}" for chunk in chunks
        )
        answer = await self.llm_client.generate(
            [
                {
                    "role": "system",
                    "content": "Answer only from the provided official context.",
                },
                {
                    "role": "user",
                    "content": f"Question: {query}\n\nOfficial context:\n{context}",
                },
            ]
        )
        return GroundedAnswer(
            answer=answer,
            citations=[chunk.source for chunk in chunks],
            confidence=max(chunk.score for chunk in chunks),
        )

