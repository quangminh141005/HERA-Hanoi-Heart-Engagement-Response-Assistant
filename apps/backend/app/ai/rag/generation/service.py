"""Grounded answer generation service."""

from __future__ import annotations

from app.ai.llm.client import LLMClient
from app.ai.observability.tracing import start_observation
from app.ai.rag.generation.evidence_validator import validate_against_evidence
from app.ai.rag.schemas import GroundedAnswer, RetrievedChunk
from app.core.config import Settings


class GenerationService:
    """Generate grounded answers from retrieved chunks."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        settings: Settings | None = None,
    ):
        self.llm_client = llm_client
        self.settings = settings

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
        deterministic_answer = "\n".join(f"• {chunk.text}" for chunk in chunks)
        generation_mode = "deterministic"
        validation_issues: list[str] = []
        exact_approved_fact = (
            len(chunks) == 1
            and chunks[0].source.document_type == "official_fact_exact"
        )
        if exact_approved_fact:
            answer = deterministic_answer
            generation_mode = "deterministic_exact"
        elif getattr(self.llm_client, "provider_name", "") == "noop":
            answer = deterministic_answer
        else:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Bạn là HERA. Trả lời đúng câu hỏi, ngắn gọn bằng "
                        "tiếng Việt và chỉ dùng những fact liên quan trực tiếp "
                        "trong context. "
                        "Không liệt kê fact không liên quan; không thêm giá, lịch, "
                        "bác sĩ, URL, số điện thoại, chẩn đoán hoặc lời khuyên "
                        "điều trị ngoài context. Nếu context không đủ thì nói "
                        "không đủ dữ liệu."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Câu hỏi: {query}\n\nFact đã duyệt:\n{context}",
                },
            ]
            generated = await self._generate_with_trace(
                messages,
                temperature=0.0,
                max_tokens=(
                    self.settings.RAG_GENERATION_MAX_TOKENS
                    if self.settings is not None
                    else 192
                ),
            )
            validation = validate_against_evidence(
                generated,
                query=query,
                evidence=[chunk.text for chunk in chunks],
            )
            if generated.startswith("HERA chưa được cấu hình LLM"):
                answer = deterministic_answer
                validation_issues = ["provider_fallback"]
            elif validation.allowed:
                answer = generated
                generation_mode = "model_validated"
            else:
                # A direct approved fact is safer than displaying an unsupported
                # paraphrase. The model output is discarded and never persisted.
                answer = deterministic_answer
                validation_issues = list(validation.issues)
        return GroundedAnswer(
            answer=answer,
            citations=[chunk.source for chunk in chunks],
            record_ids=[chunk.chunk_id for chunk in chunks],
            confidence=max(chunk.score for chunk in chunks),
            generation_mode=generation_mode,
            validation_issues=validation_issues,
        )

    async def _generate_with_trace(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if self.settings is None:
            return await self.llm_client.generate(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        with start_observation(
            "hera.rag.generation_stage",
            settings=self.settings,
            as_type="span",
            metadata={
                "provider": self.settings.LLM_PROVIDER,
                "model": self.settings.FPT_LLM_MODEL,
                "max_tokens": max_tokens,
                "model_generation_requested": True,
                "content_capture": False,
            },
        ) as observation:
            try:
                result = await self.llm_client.generate(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                observation.update(
                    metadata={
                        "result": "error",
                        "error_type": exc.__class__.__name__,
                    }
                )
                raise
            observation.update(metadata={"result": "success"})
            return result

