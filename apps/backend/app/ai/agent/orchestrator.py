"""Conversation orchestration for HERA."""

from __future__ import annotations

import asyncio
import inspect
import re
import unicodedata
from dataclasses import dataclass, field, replace
from uuid import uuid4

from app.ai.emergency.detector import (
    EmergencyAssessment,
    EmergencyDetector,
    build_emergency_response,
)
from app.ai.guardrails.pipeline import GuardrailPipeline
from app.ai.handoff.service import HandoffService
from app.ai.intent import HospitalIntent, IntentClassification, IntentClassifier
from app.ai.llm.client import build_llm_client
from app.ai.memory import (
    ConversationEntities,
    EntityMemoryStore,
    EphemeralEntityMemoryStore,
    RedisEntityMemoryStore,
)
from app.ai.privacy import redact_pii
from app.ai.rag.embeddings.embedder import build_embedder
from app.ai.rag.generation.service import GenerationService
from app.ai.rag.pipeline import RAGPipeline
from app.ai.rag.retrieval.service import RetrievalService
from app.ai.routing import ModelRoutingAssessor
from app.core.config import Settings
from app.observability.prometheus import record_upstream_failure
from app.services.structured import StructuredDataService


@dataclass(frozen=True)
class OrchestratorResult:
    """Result returned by the conversation orchestrator."""

    conversation_id: str
    response: str
    intent: str
    response_type: str = "grounded_answer"
    grounded: bool = False
    data_classification: str = "non_factual"
    citations: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    structured_record_ids: list[str] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    requires_handoff: bool = False
    emergency: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _RoutingDecision:
    emergency: EmergencyAssessment
    classification: IntentClassification
    decision_source: str
    model_emergency_confidence: float | None = None
    model_intent_confidence: float | None = None


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
        handoff_service: HandoffService,
        structured_data_service: StructuredDataService,
        memory_store: EntityMemoryStore,
        routing_model_assessor: ModelRoutingAssessor | None = None,
    ) -> None:
        self.settings = settings
        self.guardrails = guardrails
        self.emergency_detector = emergency_detector
        self.intent_classifier = intent_classifier
        self.rag_pipeline = rag_pipeline
        self.handoff_service = handoff_service
        self.structured_data_service = structured_data_service
        self.memory_store = memory_store
        self.routing_model_assessor = routing_model_assessor

    async def handle(
        self,
        *,
        message: str,
        conversation_id: str | None,
        locale: str,
        user_context: dict,
    ) -> OrchestratorResult:
        """Handle one user turn."""

        del user_context
        cid = conversation_id or uuid4().hex

        # Redaction is the boundary before any safety check or external model call.
        # An obvious emergency must win over prompt injection without contacting
        # the model; every other blocked input must stop before model routing.
        redaction = redact_pii(message)
        emergency_precheck = self.emergency_detector.assess(redaction.text)
        if emergency_precheck.is_emergency:
            routing = _RoutingDecision(
                emergency=emergency_precheck,
                classification=IntentClassification(
                    intent=HospitalIntent.EMERGENCY,
                    confidence=emergency_precheck.confidence,
                    reasons=emergency_precheck.matched_terms,
                ),
                decision_source="deterministic_safety_precheck",
            )
        else:
            input_check = self.guardrails.validate_input(redaction.text)
            if not input_check.allowed:
                return self._refusal(
                    cid,
                    intent=HospitalIntent.UNSUPPORTED.value,
                    response=(
                        "HERA không thể thực hiện yêu cầu này. Vui lòng chỉ hỏi thông "
                        "tin hành chính từ dữ liệu của Bệnh viện."
                    ),
                    metadata={
                        "guardrail_violation": input_check.violation_type,
                        "decision_source": "input_guardrail",
                    },
                )

            sanitized = input_check.text
            routing = await self._assess_routing(sanitized)

        emergency = routing.emergency

        def finish(result: OrchestratorResult) -> OrchestratorResult:
            return _mark_routing_decision(result, routing)

        if emergency.is_emergency:
            await self.memory_store.clear(cid)
            template = self.structured_data_service.active_template("emergency")
            response = template or build_emergency_response(
                emergency_hotline=self.settings.EMERGENCY_HOTLINE,
                hospital_hotline=self.settings.HOSPITAL_HOTLINE,
            )
            sources = self.structured_data_service.repository.get_sources_by_ids(
                ["SRC-BOOKING-GUIDE"]
            )
            source = sources.get("SRC-BOOKING-GUIDE")
            citations = []
            if source is not None:
                citations.append(
                    {
                        "source_id": source["source_id"],
                        "title": source["title"],
                        "url": source["url"],
                        "excerpt": None,
                    }
                )
            return finish(
                OrchestratorResult(
                    conversation_id=cid,
                    response=response,
                    intent=HospitalIntent.EMERGENCY.value,
                    response_type="emergency_handoff",
                    grounded=bool(citations),
                    data_classification="official_current",
                    citations=citations,
                    actions=[
                        {
                            "type": "call",
                            "channel_id": "EMERGENCY-115",
                            "label_vi": "Gọi cấp cứu 115",
                            "target": self.settings.EMERGENCY_HOTLINE,
                        }
                    ],
                    emergency=True,
                    requires_handoff=True,
                    metadata={"reasons": emergency.matched_terms},
                )
            )

        classification = routing.classification
        context = await self.memory_store.load(cid)
        sanitized, classification, context_applied = _apply_safe_context(
            sanitized,
            classification,
            context,
        )
        if (
            context is not None
            and not context_applied
            and classification.intent.value != context.intent
            and classification.intent
            not in {HospitalIntent.GREETING, HospitalIntent.THANKS}
        ):
            await self.memory_store.clear(cid)

        if classification.intent is HospitalIntent.GREETING:
            return finish(
                OrchestratorResult(
                    conversation_id=cid,
                    response=(
                        "Xin chào, mình là HERA. Mình có thể hỗ trợ thông tin hành chính, "
                        "quy trình khám, BHYT, lịch khám và hướng dẫn liên hệ chính thức "
                        "của Bệnh viện Tim Hà Nội."
                    ),
                    intent=classification.intent.value,
                    warnings=self._pii_warnings(redaction.categories),
                )
            )

        if classification.intent is HospitalIntent.THANKS:
            return finish(
                OrchestratorResult(
                    conversation_id=cid,
                    response="Rất vui được hỗ trợ bạn.",
                    intent=classification.intent.value,
                    warnings=self._pii_warnings(redaction.categories),
                )
            )

        if classification.intent is HospitalIntent.HUMAN_HANDOFF:
            return finish(
                self._refusal(
                    cid,
                    intent=classification.intent.value,
                    response=(
                        "Bạn có thể liên hệ trực tiếp các kênh hỗ trợ chính thức "
                        "bên dưới."
                    ),
                )
            )

        if classification.intent is HospitalIntent.INSURANCE_PERSONAL_BENEFIT:
            return finish(
                self._refusal(
                    cid,
                    intent=classification.intent.value,
                    response=(
                        "Dữ liệu hiện có chỉ gồm mức đóng BHYT hộ gia đình, không đủ "
                        "để xác định quyền lợi, tỷ lệ chi trả hoặc mức hưởng cá nhân."
                    ),
                )
            )

        if classification.intent is HospitalIntent.PRICE_BHYT_CALCULATION:
            return finish(
                self._refusal(
                    cid,
                    intent=classification.intent.value,
                    response=(
                        "HERA không ghép bảng giá với mức đóng BHYT để tính hóa đơn "
                        "hoặc số tiền người bệnh phải trả."
                    ),
                )
            )

        if classification.intent is HospitalIntent.SERVICE_PRICE:
            result = await asyncio.to_thread(
                self.structured_data_service.chat_service_price,
                sanitized,
            )
            response = self._structured_result(cid, result, redaction.categories)
            await self._remember_structured(cid, result)
            return finish(_mark_context_applied(response, context_applied))

        if classification.intent is HospitalIntent.INSURANCE:
            result = await asyncio.to_thread(
                self.structured_data_service.chat_bhyt,
                sanitized,
            )
            response = self._structured_result(cid, result, redaction.categories)
            await self._remember_structured(cid, result)
            return finish(_mark_context_applied(response, context_applied))

        if classification.intent is HospitalIntent.DOCTOR_SCHEDULE:
            result = await asyncio.to_thread(
                self.structured_data_service.chat_schedule,
                sanitized,
            )
            response = self._structured_result(cid, result, redaction.categories)
            await self._remember_structured(cid, result)
            return finish(_mark_context_applied(response, context_applied))

        try:
            async with asyncio.timeout(self.settings.CHAT_OVERALL_TIMEOUT_SECONDS):
                answer = await self.rag_pipeline.answer(
                    sanitized,
                    locale=locale,
                    top_k=self.settings.RAG_TOP_K,
                    allowed_intents={classification.intent.value},
                )
        except TimeoutError as exc:
            record_upstream_failure("rag_pipeline", exc)
            return finish(
                self._refusal(
                    cid,
                    intent=classification.intent.value,
                    response=(
                        "HERA chưa thể hoàn tất tra cứu trong thời gian an toàn. "
                        "Bạn vui lòng thử lại hoặc dùng kênh hỗ trợ chính thức."
                    ),
                    metadata={"upstream_timeout": "rag_pipeline"},
                )
            )
        citations = []
        seen_source_ids: set[str] = set()
        for source in answer.citations:
            if source.source_id in seen_source_ids:
                continue
            seen_source_ids.add(source.source_id)
            citations.append(
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "url": source.url,
                    "excerpt": None,
                }
            )
        if not citations:
            return finish(
                self._refusal(
                    cid,
                    intent=classification.intent.value,
                    response=(
                        "Hiện HERA chưa có fact đủ phù hợp trong bộ dữ liệu đã duyệt "
                        "để trả lời câu hỏi này."
                    ),
                    metadata={"retrieval_confidence": answer.confidence},
                )
            )

        output_check = self.guardrails.validate_output(
            answer.answer,
            has_citations=bool(citations),
            requires_grounding=True,
        )
        if not output_check.allowed:
            return finish(
                self._refusal(
                    cid,
                    intent=classification.intent.value,
                    response=(
                        "Câu trả lời chưa vượt qua kiểm tra nguồn nên HERA không "
                        "hiển thị."
                    ),
                    metadata={
                        "guardrail_violation": output_check.violation_type,
                    },
                )
            )

        response = OrchestratorResult(
            conversation_id=cid,
            response=answer.answer,
            intent=classification.intent.value,
            response_type="grounded_answer",
            grounded=True,
            data_classification="official_current",
            citations=citations,
            warnings=self._pii_warnings(redaction.categories),
            structured_record_ids=answer.record_ids,
            actions=(
                list(self.structured_data_service.support_actions())
                if classification.intent is HospitalIntent.APPOINTMENT
                else []
            ),
            metadata={
                "confidence": answer.confidence,
                "classification_confidence": classification.confidence,
                "generation_mode": answer.generation_mode,
                "evidence_validation_issues": answer.validation_issues,
            },
        )

        await self.memory_store.put(
            cid,
            ConversationEntities(
                intent=classification.intent.value,
                record_ids=tuple(answer.record_ids),
            ),
        )
        return finish(_mark_context_applied(response, context_applied))

    async def _assess_routing(self, message: str) -> _RoutingDecision:
        """Use one model call for safety and intent, with deterministic fallback."""

        deterministic_emergency = self.emergency_detector.assess(message)
        deterministic_classification = self.intent_classifier.classify(message)
        if self.routing_model_assessor is None:
            return _RoutingDecision(
                emergency=deterministic_emergency,
                classification=deterministic_classification,
                decision_source="deterministic_fallback",
            )

        try:
            model_assessment = await self.routing_model_assessor.assess(message)
        except Exception as exc:
            record_upstream_failure("routing_model_assessor", exc)
            return _RoutingDecision(
                emergency=deterministic_emergency,
                classification=deterministic_classification,
                decision_source="deterministic_fallback",
            )

        confidence_kwargs = {
            "model_emergency_confidence": model_assessment.emergency_confidence,
            "model_intent_confidence": model_assessment.intent_confidence,
        }
        if model_assessment.emergency.is_emergency:
            classification = model_assessment.classification or IntentClassification(
                intent=HospitalIntent.EMERGENCY,
                confidence=model_assessment.emergency.confidence,
                reasons=model_assessment.emergency.matched_terms,
            )
            return _RoutingDecision(
                emergency=model_assessment.emergency,
                classification=classification,
                decision_source="model",
                **confidence_kwargs,
            )

        # Keep a high-sensitivity local safety net if the model misses an obvious
        # emergency phrase or the provider returns an overconfident false negative.
        if deterministic_emergency.is_emergency:
            return _RoutingDecision(
                emergency=deterministic_emergency,
                classification=deterministic_classification,
                decision_source="deterministic_safety_fallback",
                **confidence_kwargs,
            )

        if model_assessment.classification is not None:
            return _RoutingDecision(
                emergency=model_assessment.emergency,
                classification=model_assessment.classification,
                decision_source="model",
                **confidence_kwargs,
            )
        return _RoutingDecision(
            emergency=deterministic_emergency,
            classification=deterministic_classification,
            decision_source="deterministic_fallback",
            **confidence_kwargs,
        )

    async def close(self) -> None:
        """Close process-scoped Redis and model HTTP clients."""

        self.structured_data_service.close()
        resources = (
            self.memory_store,
            self.rag_pipeline.retrieval_service.embedder,
            self.rag_pipeline.generation_service.llm_client,
        )
        for resource in resources:
            close = getattr(resource, "close", None)
            if not callable(close):
                continue
            result = close()
            if inspect.isawaitable(result):
                await result

    async def _remember_structured(self, cid, result) -> None:
        """Retain only canonical entities returned by approved structured data."""

        payload = result.metadata.get("structured_action", {})
        if not isinstance(payload, dict):
            payload = {}
        rows = payload.get("records", [])
        first = rows[0] if rows and isinstance(rows[0], dict) else {}
        intent = result.intent
        facility = first.get("facility_code") or payload.get("facility_code")
        service_name = None
        service_date = None
        doctor_name = None
        bhyt_tier = None

        if intent == HospitalIntent.SERVICE_PRICE.value:
            service_name = first.get("display_name")
        elif intent == HospitalIntent.DOCTOR_SCHEDULE.value:
            service_date = first.get("service_date") or payload.get("service_date")
            doctor_name = first.get("provider_text")
        elif intent == HospitalIntent.INSURANCE.value:
            selected_ids = set(result.structured_record_ids)
            for tier in payload.get("tiers", []):
                if isinstance(tier, dict) and tier.get("tier_id") in selected_ids:
                    bhyt_tier = tier.get("tier_order")
                    break

        await self.memory_store.put(
            cid,
            ConversationEntities(
                intent=intent,
                facility_code=facility,
                service_name=service_name,
                service_date=service_date,
                doctor_name=doctor_name,
                bhyt_tier=bhyt_tier,
                record_ids=tuple(result.structured_record_ids),
            ),
        )

    def _structured_result(self, cid, result, pii_categories) -> OrchestratorResult:
        citations = [citation.model_dump() for citation in result.citations]
        output_check = self.guardrails.validate_output(
            result.response,
            has_citations=bool(citations),
            requires_grounding=result.grounded,
        )
        if not output_check.allowed:
            return self._refusal(
                cid,
                intent=result.intent,
                response=(
                    "Kết quả dữ liệu không vượt qua kiểm tra nguồn nên chưa thể "
                    "hiển thị."
                ),
                metadata={"guardrail_violation": output_check.violation_type},
            )
        return OrchestratorResult(
            conversation_id=cid,
            response=result.response,
            intent=result.intent,
            response_type=result.response_type,
            grounded=result.grounded,
            data_classification=result.data_classification,
            citations=citations,
            warnings=[*result.warnings, *self._pii_warnings(pii_categories)],
            structured_record_ids=list(result.structured_record_ids),
            actions=list(result.actions),
            requires_handoff=result.requires_handoff,
            metadata=result.metadata,
        )

    def _refusal(
        self,
        cid: str,
        *,
        intent: str,
        response: str,
        metadata: dict | None = None,
    ) -> OrchestratorResult:
        return OrchestratorResult(
            conversation_id=cid,
            response=response,
            intent=intent,
            response_type="refusal_and_handoff",
            grounded=False,
            data_classification="insufficient_data",
            actions=list(self.structured_data_service.support_actions()),
            requires_handoff=True,
            metadata=metadata or {},
        )

    @staticmethod
    def _pii_warnings(categories) -> list[str]:
        if not categories:
            return []
        return [
            "HERA đã ẩn thông tin nhận dạng trong câu hỏi; vui lòng không gửi thêm "
            "số điện thoại, CCCD hoặc mã thẻ BHYT qua chat."
        ]


def build_default_orchestrator(settings: Settings) -> ConversationOrchestrator:
    """Build the configured PostgreSQL, FPT and safety orchestration pipeline."""

    emergency_detector = EmergencyDetector()
    llm_client = build_llm_client(settings)
    structured_service = StructuredDataService(settings)
    return ConversationOrchestrator(
        settings=settings,
        guardrails=GuardrailPipeline(),
        emergency_detector=emergency_detector,
        intent_classifier=IntentClassifier(emergency_detector),
        rag_pipeline=RAGPipeline(
            retrieval_service=RetrievalService(
                structured_service.repository,
                embedder=build_embedder(settings),
                minimum_semantic_score=settings.RAG_MIN_CONFIDENCE,
                shared_cache=structured_service.cache,
                embedding_model=settings.FPT_EMBEDDING_MODEL,
                expected_embedding_dimensions=settings.EMBEDDING_DIMENSIONS,
                settings=settings,
            ),
            generation_service=GenerationService(llm_client, settings=settings),
        ),
        handoff_service=HandoffService(settings.HOSPITAL_HOTLINE),
        structured_data_service=structured_service,
        memory_store=(
            RedisEntityMemoryStore(
                redis_url=settings.REDIS_URL,
                ttl_minutes=settings.EPHEMERAL_CONTEXT_TTL_MINUTES,
            )
            if settings.CONVERSATION_MEMORY_BACKEND == "redis"
            else EphemeralEntityMemoryStore(
                ttl_minutes=settings.EPHEMERAL_CONTEXT_TTL_MINUTES,
            )
        ),
        routing_model_assessor=(
            ModelRoutingAssessor(
                llm_client=llm_client,
                settings=settings,
                timeout_seconds=settings.MODEL_ROUTING_TIMEOUT_SECONDS,
                max_tokens=settings.MODEL_ROUTING_MAX_TOKENS,
                emergency_confidence_threshold=(
                    settings.MODEL_ROUTING_EMERGENCY_CONFIDENCE_THRESHOLD
                ),
                intent_confidence_threshold=(
                    settings.MODEL_ROUTING_INTENT_CONFIDENCE_THRESHOLD
                ),
            )
            if settings.MODEL_ROUTING_ENABLED and settings.LLM_PROVIDER != "noop"
            else None
        ),
    )


_FOLLOW_UP_MARKERS = (
    "ai ",
    "bac si do",
    "bao nhieu",
    "ben do",
    "ca do",
    "cai do",
    "con ",
    "cho do",
    "thi sao",
    "ngay mai",
    "ngay kia",
    "ngay do",
    "o do",
    "tuan sau",
    "tuan nay",
    "co so 1",
    "co so 2",
    "nguoi thu",
    "dich vu do",
    "luc nao",
    "the con",
    "the thi sao",
    "vay",
)
_STRUCTURED_CONTEXT_INTENTS = {
    HospitalIntent.SERVICE_PRICE,
    HospitalIntent.INSURANCE,
    HospitalIntent.DOCTOR_SCHEDULE,
}


def _apply_safe_context(
    message: str,
    classification: IntentClassification,
    context: ConversationEntities | None,
) -> tuple[str, IntentClassification, bool]:
    """Resolve elliptical follow-ups using only approved canonical entities."""

    if context is None or not _looks_like_follow_up(message):
        return message, classification, False
    try:
        previous_intent = HospitalIntent(context.intent)
    except ValueError:
        return message, classification, False
    if previous_intent not in _STRUCTURED_CONTEXT_INTENTS:
        return message, classification, False
    if classification.intent is HospitalIntent.GENERAL_SUPPORT:
        classification = IntentClassification(
            intent=previous_intent,
            confidence=0.7,
            reasons=["ephemeral approved-entity context"],
        )
    elif classification.intent is not previous_intent:
        return message, classification, False

    folded = _fold_text(message)
    parts: list[str] = []
    if previous_intent is HospitalIntent.SERVICE_PRICE:
        parts.append("giá")
        if context.service_name and not _has_explicit_service(message):
            parts.append(context.service_name)
    elif previous_intent is HospitalIntent.INSURANCE:
        parts.append("mức đóng BHYT hộ gia đình")
        if context.bhyt_tier and "nguoi thu" not in folded:
            parts.append(f"người thứ {context.bhyt_tier}")
    elif previous_intent is HospitalIntent.DOCTOR_SCHEDULE:
        parts.append("lịch bác sĩ")
        if context.doctor_name and not _has_explicit_doctor(message):
            parts.append(context.doctor_name)
        if context.service_date and not _has_date_reference(message):
            parts.append(f"ngày {context.service_date}")
    if context.facility_code and not _has_facility(message):
        parts.append(context.facility_code)
    parts.append(message)
    return " ".join(parts), classification, True


def _looks_like_follow_up(message: str) -> bool:
    folded = f"{_fold_text(message)} "
    if any(marker in folded for marker in _FOLLOW_UP_MARKERS):
        return True
    tokens = re.findall(r"[a-z0-9]+", folded)
    weak_words = {
        "ai",
        "bao",
        "bao nhieu",
        "co",
        "con",
        "khong",
        "la",
        "nao",
        "o",
        "sao",
        "thi",
        "the",
        "vay",
    }
    return 0 < len(tokens) <= 5 and any(token in weak_words for token in tokens)


def _has_facility(message: str) -> bool:
    return bool(re.search(r"\b(?:cs|co so)\s*[12]\b", _fold_text(message)))


def _has_date_reference(message: str) -> bool:
    folded = _fold_text(message)
    return bool(
        re.search(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", folded)
        or re.search(r"\b\d{1,2}[-/]\d{1,2}[-/]20\d{2}\b", folded)
        or any(term in folded for term in ("hom nay", "ngay mai", "ngay kia", "tuan"))
    )


def _has_explicit_service(message: str) -> bool:
    folded = _fold_text(message)
    tokens = set(re.findall(r"[a-z0-9]+", folded))
    filler = {
        "1",
        "2",
        "bao",
        "chi",
        "co",
        "con",
        "do",
        "dich",
        "gia",
        "la",
        "nhieu",
        "phi",
        "sao",
        "so",
        "thi",
        "vu",
    }
    return bool(tokens - filler)


def _has_explicit_doctor(message: str) -> bool:
    folded = _fold_text(message)
    return bool(re.search(r"\b(?:bac si|bs)\s+\w+\s+\w+", folded))


def _fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.lower())
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return without_marks.replace("đ", "d")


def _mark_context_applied(
    result: OrchestratorResult,
    context_applied: bool,
) -> OrchestratorResult:
    if not context_applied:
        return result
    return replace(
        result,
        metadata={**result.metadata, "ephemeral_context_applied": True},
    )


def _mark_routing_decision(
    result: OrchestratorResult,
    routing: _RoutingDecision,
) -> OrchestratorResult:
    routing_metadata: dict[str, object] = {
        "decision_source": routing.decision_source,
    }
    if routing.model_emergency_confidence is not None:
        routing_metadata["model_emergency_confidence"] = (
            routing.model_emergency_confidence
        )
    if routing.model_intent_confidence is not None:
        routing_metadata["model_intent_confidence"] = routing.model_intent_confidence
    return replace(
        result,
        metadata={**result.metadata, **routing_metadata},
    )
