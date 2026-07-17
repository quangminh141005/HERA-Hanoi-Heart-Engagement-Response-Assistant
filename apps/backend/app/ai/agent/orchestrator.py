"""Conversation orchestration for HERA."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from app.ai.emergency.detector import EmergencyDetector, build_emergency_response
from app.ai.guardrails.pipeline import GuardrailPipeline
from app.ai.handoff.service import HandoffService
from app.ai.intent import HospitalIntent, IntentClassifier
from app.ai.llm.client import build_llm_client
from app.ai.rag.generation.service import GenerationService
from app.ai.rag.pipeline import RAGPipeline
from app.ai.rag.retrieval.service import RetrievalService
from app.ai.tools.hospital_api import HospitalApiClient
from app.core.config import Settings


@dataclass(frozen=True)
class OrchestratorResult:
    """Result returned by the conversation orchestrator."""

    conversation_id: str
    response: str
    intent: str
    citations: list[dict] = field(default_factory=list)
    requires_handoff: bool = False
    emergency: bool = False
    metadata: dict = field(default_factory=dict)


class ConversationOrchestrator:
    """Route each chat turn through safety, tools, RAG, and handoff."""

    def __init__(
        self,
        *,
        settings: Settings,
        guardrails: GuardrailPipeline,
        emergency_detector: EmergencyDetector,
        intent_classifier: IntentClassifier,
        rag_pipeline: RAGPipeline,
        hospital_api: HospitalApiClient,
        handoff_service: HandoffService,
    ) -> None:
        self.settings = settings
        self.guardrails = guardrails
        self.emergency_detector = emergency_detector
        self.intent_classifier = intent_classifier
        self.rag_pipeline = rag_pipeline
        self.hospital_api = hospital_api
        self.handoff_service = handoff_service

    async def handle(
        self,
        *,
        message: str,
        conversation_id: str | None,
        locale: str,
        user_context: dict,
    ) -> OrchestratorResult:
        """Handle one user turn."""

        cid = conversation_id or uuid4().hex
        input_check = self.guardrails.validate_input(message)
        if not input_check.allowed:
            return OrchestratorResult(
                conversation_id=cid,
                response=(
                    "Mình không thể xử lý yêu cầu này vì lý do an toàn. "
                    "Vui lòng đặt câu hỏi về thông tin hành chính hoặc "
                    "dịch vụ bệnh viện."
                ),
                intent=HospitalIntent.UNSUPPORTED.value,
                metadata={
                    "guardrail_violation": input_check.violation_type,
                    "reason": input_check.reason,
                },
            )

        sanitized = input_check.text
        classification = self.intent_classifier.classify(sanitized)

        if classification.intent is HospitalIntent.EMERGENCY:
            return OrchestratorResult(
                conversation_id=cid,
                response=build_emergency_response(
                    emergency_hotline=self.settings.EMERGENCY_HOTLINE,
                    hospital_hotline=self.settings.HOSPITAL_HOTLINE,
                ),
                intent=classification.intent.value,
                emergency=True,
                requires_handoff=True,
                metadata={"reasons": classification.reasons},
            )

        if classification.intent is HospitalIntent.GREETING:
            return OrchestratorResult(
                conversation_id=cid,
                response=(
                    "Xin chào, mình là HERA. Mình có thể hỗ trợ thông tin hành chính, "
                    "quy trình khám, BHYT, lịch khám và hướng dẫn liên hệ chính thức "
                    "của Bệnh viện Tim Hà Nội."
                ),
                intent=classification.intent.value,
            )

        if classification.intent is HospitalIntent.THANKS:
            return OrchestratorResult(
                conversation_id=cid,
                response="Rất vui được hỗ trợ bạn.",
                intent=classification.intent.value,
            )

        if classification.intent is HospitalIntent.HUMAN_HANDOFF:
            decision = self.handoff_service.required(
                "Người dùng yêu cầu hỗ trợ trực tiếp."
            )
            return OrchestratorResult(
                conversation_id=cid,
                response=self.handoff_service.format_message(decision),
                intent=classification.intent.value,
                requires_handoff=True,
            )

        if classification.requires_hospital_api:
            return await self._handle_hospital_api_intent(
                cid,
                sanitized,
                classification.intent,
                user_context,
            )

        answer = await self.rag_pipeline.answer(
            sanitized,
            locale=locale,
            top_k=self.settings.RAG_TOP_K,
        )
        citations = [
            {
                "source_id": source.source_id,
                "title": source.title,
                "url": source.url,
                "excerpt": None,
            }
            for source in answer.citations
        ]
        output_check = self.guardrails.validate_output(
            answer.answer,
            has_citations=bool(citations),
            requires_grounding=classification.requires_rag,
        )
        if not output_check.allowed:
            decision = self.handoff_service.required(
                "Câu trả lời cần nguồn chính thức hoặc kiểm duyệt thêm."
            )
            return OrchestratorResult(
                conversation_id=cid,
                response=self.handoff_service.format_message(decision),
                intent=classification.intent.value,
                requires_handoff=True,
                metadata={
                    "guardrail_violation": output_check.violation_type,
                    "reason": output_check.reason,
                },
            )

        return OrchestratorResult(
            conversation_id=cid,
            response=answer.answer,
            intent=classification.intent.value,
            citations=citations,
            metadata={
                "confidence": answer.confidence,
                "classification_confidence": classification.confidence,
            },
        )

    async def _handle_hospital_api_intent(
        self,
        conversation_id: str,
        message: str,
        intent: HospitalIntent,
        user_context: dict,
    ) -> OrchestratorResult:
        context = {"message": message, **user_context}
        if intent is HospitalIntent.APPOINTMENT:
            api_result = await self.hospital_api.lookup_appointment(context)
        elif intent is HospitalIntent.DOCTOR_SCHEDULE:
            api_result = await self.hospital_api.lookup_doctor_schedule(context)
        else:
            api_result = await self.hospital_api.lookup_service_price(context)

        if api_result.success:
            return OrchestratorResult(
                conversation_id=conversation_id,
                response=str(api_result.data),
                intent=intent.value,
                metadata={"source": api_result.source},
            )

        decision = self.handoff_service.required(
            "Dữ liệu thời gian thực cần API bệnh viện nhưng API chưa được cấu hình."
        )
        return OrchestratorResult(
            conversation_id=conversation_id,
            response=(
                f"{api_result.message} "
                f"{self.handoff_service.format_message(decision)}"
            ),
            intent=intent.value,
            requires_handoff=True,
            metadata={"todo": "Configure official hospital API integration."},
        )


def build_default_orchestrator(settings: Settings) -> ConversationOrchestrator:
    """Build the default orchestrator using placeholder integrations."""

    emergency_detector = EmergencyDetector()
    llm_client = build_llm_client(settings)
    return ConversationOrchestrator(
        settings=settings,
        guardrails=GuardrailPipeline(),
        emergency_detector=emergency_detector,
        intent_classifier=IntentClassifier(emergency_detector),
        rag_pipeline=RAGPipeline(
            retrieval_service=RetrievalService(),
            generation_service=GenerationService(llm_client),
        ),
        hospital_api=HospitalApiClient(),
        handoff_service=HandoffService(settings.HOSPITAL_HOTLINE),
    )
