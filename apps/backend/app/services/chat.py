"""Chat orchestration service."""

from __future__ import annotations

import asyncio
import logging

from app.ai.agent.orchestrator import build_default_orchestrator
from app.ai.intent import HospitalIntent
from app.ai.observability.tracing import start_observation
from app.core.config import Settings
from app.observability.prometheus import (
    AI_RESPONSES_TOTAL,
    EMERGENCY_HANDOFFS_TOTAL,
    GROUNDING_FAILURES_TOTAL,
    GUARDRAIL_BLOCKS_TOTAL,
    REQUESTS_TOTAL,
)
from app.persistence import ChatPersistenceRepository
from app.schemas.chat import ChatRequest, ChatResponse, Citation

logger = logging.getLogger(__name__)


class ChatService:
    """Application service for assistant chat requests."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.orchestrator = build_default_orchestrator(settings)
        self.persistence = ChatPersistenceRepository(
            retention_days=settings.CONSENTED_MESSAGE_TTL_DAYS,
        )

    async def respond(self, request: ChatRequest, *, request_id: str) -> ChatResponse:
        """Process a chat request through the HERA assistant pipeline."""

        trace_metadata = {
            "request_id": request_id,
            "channel": _safe_trace_channel(request.client_context.get("channel")),
            "consent_to_store": request.consent_to_store,
            "configured_llm_model": self.settings.FPT_LLM_MODEL,
            "configured_embedding_model": self.settings.EMBEDDING_MODEL,
        }
        trace_kwargs = {}
        if self.settings.LANGFUSE_CAPTURE_CONTENT:
            trace_kwargs["input"] = _chat_trace_input(request)
        with start_observation(
            "hera.chat_turn",
            settings=self.settings,
            as_type="agent",
            metadata=trace_metadata,
            **trace_kwargs,
        ) as observation:
            result = await self.orchestrator.handle(
                message=request.message,
                conversation_id=request.conversation_id,
                locale=request.locale,
                user_context={**request.client_context, **request.user_context},
            )
            response = ChatResponse(
                request_id=request_id,
                conversation_id=result.conversation_id,
                response=result.response,
                answer_vi=result.response,
                response_type=result.response_type,
                intent=result.intent,
                grounded=result.grounded,
                data_classification=result.data_classification,
                citations=[Citation(**source) for source in result.citations],
                warnings=result.warnings,
                structured_record_ids=result.structured_record_ids,
                actions=result.actions,
                requires_handoff=result.requires_handoff,
                emergency=result.emergency,
                metadata=result.metadata,
            )
            await asyncio.to_thread(
                self.persistence.record_chat_turn,
                request_id=request_id,
                conversation_id=result.conversation_id,
                consent_to_store=request.consent_to_store,
                user_content=request.message,
                assistant_content=result.response,
                response_type=result.response_type,
                data_classification=result.data_classification,
                grounded=result.grounded,
                intent=result.intent,
                citations=result.citations,
                structured_record_ids=result.structured_record_ids,
            )
            AI_RESPONSES_TOTAL.labels(
                response_type=result.response_type,
                grounded=str(bool(result.grounded)).lower(),
            ).inc()
            request_result = _request_result(result)
            REQUESTS_TOTAL.labels(
                intent=_safe_intent(result.intent),
                result=request_result,
            ).inc()
            grounding_reason = _grounding_failure_reason(result)
            if grounding_reason:
                GROUNDING_FAILURES_TOTAL.labels(reason=grounding_reason).inc()
            if result.emergency:
                EMERGENCY_HANDOFFS_TOTAL.inc()
            violation_type = result.metadata.get("guardrail_violation")
            if violation_type:
                GUARDRAIL_BLOCKS_TOTAL.labels(
                    violation_type=str(violation_type),
                ).inc()
            logger.info(
                "chat turn completed",
                extra={
                    "event": "chat_turn_completed",
                    "intent": _safe_intent(result.intent),
                    "result": request_result,
                    "response_type": result.response_type,
                    "grounded": bool(result.grounded),
                    "emergency": bool(result.emergency),
                },
            )
            trace_update = {
                "metadata": {
                    **trace_metadata,
                    "intent": result.intent,
                    "response_type": result.response_type,
                    "grounded": bool(result.grounded),
                    "emergency": bool(result.emergency),
                    "execution_path": _execution_path(result),
                    "generation_mode": str(
                        result.metadata.get("generation_mode", "not_applicable")
                    )[:64],
                    "decision_source": str(
                        result.metadata.get("decision_source", "unknown")
                    )[:64],
                }
            }
            if self.settings.LANGFUSE_CAPTURE_CONTENT:
                trace_update["output"] = _chat_trace_output(result)
            observation.update(**trace_update)
            return response

    async def close(self) -> None:
        await self.orchestrator.close()


_TRACE_CHANNELS = frozenset(
    {
        "hospital_web",
        "embedded_widget",
        "standalone_web",
        "widget",
        "unknown",
    }
)


def _safe_trace_channel(value: object) -> str:
    if isinstance(value, str) and value in _TRACE_CHANNELS:
        return value
    return "unknown"


def _chat_trace_input(request: ChatRequest) -> dict[str, object]:
    """Capture the user-visible chat request when trace content capture is enabled."""

    return {
        "message": request.message,
        "conversation_id": request.conversation_id,
        "locale": request.locale,
        "channel": _safe_trace_channel(request.client_context.get("channel")),
        "consent_to_store": request.consent_to_store,
    }


def _chat_trace_output(result) -> dict[str, object]:
    """Capture the user-visible assistant result when explicitly enabled."""

    return {
        "response": result.response,
        "conversation_id": result.conversation_id,
        "response_type": result.response_type,
        "intent": result.intent,
        "grounded": bool(result.grounded),
        "emergency": bool(result.emergency),
        "data_classification": result.data_classification,
        "citations": result.citations,
        "warnings": result.warnings,
        "structured_record_ids": result.structured_record_ids,
        "actions": result.actions,
        "requires_handoff": result.requires_handoff,
    }


_SAFE_INTENTS = frozenset(intent.value for intent in HospitalIntent)


def _safe_intent(value: str) -> str:
    return value if value in _SAFE_INTENTS else "unknown"


def _request_result(result) -> str:
    if result.emergency:
        return "emergency_handoff"
    if result.response_type == "refusal_and_handoff":
        return "refusal_handoff"
    if result.response_type == "structured_action":
        return "structured" if result.grounded else "no_match"
    if result.grounded:
        return "grounded"
    return "non_factual"


def _grounding_failure_reason(result) -> str | None:
    if result.response_type == "structured_action" and not result.grounded:
        return "no_structured_match"
    if "retrieval_confidence" in result.metadata:
        return "missing_citation"
    if result.metadata.get("guardrail_violation"):
        return "output_guardrail"
    return None


def _execution_path(result) -> str:
    if result.emergency:
        return "emergency_safety_handoff"
    if result.response_type == "structured_action":
        return "postgresql_structured_lookup"
    generation_mode = str(result.metadata.get("generation_mode", ""))
    if generation_mode == "model_validated":
        return "rag_model_validated"
    if generation_mode:
        return f"rag_{generation_mode}"[:64]
    if result.response_type == "refusal_and_handoff":
        return "guardrail_or_handoff"
    return "deterministic_control_message"
