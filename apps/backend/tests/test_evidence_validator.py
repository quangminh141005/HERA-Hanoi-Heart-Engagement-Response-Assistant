from __future__ import annotations

import asyncio

from app.ai.rag.generation.evidence_validator import validate_against_evidence
from app.ai.rag.generation.service import GenerationService
from app.ai.rag.schemas import KnowledgeSource, RetrievedChunk


class StubLLM:
    provider_name = "openai"

    def __init__(self, answer: str) -> None:
        self.answer = answer

    async def generate(self, messages, **kwargs):
        del messages, kwargs
        return self.answer


def _chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="CHUNK-FACT-001",
        text=text,
        score=0.9,
        source=KnowledgeSource(source_id="SRC-1", title="Nguồn đã duyệt"),
    )


def test_validator_rejects_new_phone_number_and_amount() -> None:
    result = validate_against_evidence(
        "Hãy gọi 19009999 và thanh toán 500.000 đồng.",
        query="Liên hệ ở đâu?",
        evidence=["Kênh hỗ trợ được công bố là 19001082."],
    )

    assert result.allowed is False
    assert "unsupported_phone" in result.issues
    assert "unsupported_number" in result.issues


def test_generation_discards_unsupported_model_claim() -> None:
    fact = "Kênh đăng ký khám được công bố là 19001082."
    service = GenerationService(StubLLM("Hãy gọi số 19009999 để đặt lịch."))

    result = asyncio.run(service.generate("Số đặt lịch là gì?", [_chunk(fact)]))

    assert result.answer == f"• {fact}"
    assert result.generation_mode == "deterministic"
    assert "unsupported_phone" in result.validation_issues


def test_generation_accepts_supported_paraphrase() -> None:
    fact = "Bạn nên có mặt trước giờ khám ít nhất 15 phút."
    service = GenerationService(
        StubLLM("Bạn nên có mặt trước giờ khám ít nhất 15 phút.")
    )

    result = asyncio.run(service.generate("Tôi nên đến sớm bao lâu?", [_chunk(fact)]))

    assert result.generation_mode == "model_validated"
    assert result.validation_issues == []


def test_generation_exact_fact_does_not_call_llm() -> None:
    class ExplodingLLM:
        provider_name = "openai"

        async def generate(self, messages, **kwargs):
            del messages, kwargs
            raise AssertionError("exact approved facts must not call the model")

    fact = "Người bệnh nên có mặt trước giờ khám ít nhất 15 phút."
    chunk = _chunk(fact).model_copy(
        update={
            "source": _chunk(fact).source.model_copy(
                update={"document_type": "official_fact_exact"}
            )
        }
    )

    result = asyncio.run(
        GenerationService(ExplodingLLM()).generate("Đến sớm bao lâu?", [chunk])
    )

    assert result.answer == f"• {fact}"
    assert result.generation_mode == "deterministic_exact"
