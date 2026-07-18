"""One-call model assessment for emergency risk and chat intent."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from app.ai.emergency.detector import EmergencyAssessment
from app.ai.intent import HospitalIntent, IntentClassification
from app.ai.llm.client import LLMClient
from app.ai.observability.tracing import start_observation
from app.ai.privacy import redact_pii
from app.core.config import Settings


@dataclass(frozen=True)
class ModelRoutingAssessment:
    """Validated emergency and intent decision returned by the model."""

    emergency: EmergencyAssessment
    classification: IntentClassification | None
    emergency_confidence: float
    intent_confidence: float


@dataclass(frozen=True)
class ModelRoutingAssessor:
    """Classify emergency risk and intent with one bounded model request."""

    llm_client: LLMClient
    settings: Settings
    timeout_seconds: float
    max_tokens: int
    emergency_confidence_threshold: float
    intent_confidence_threshold: float

    async def assess(self, message: str) -> ModelRoutingAssessment:
        """Return a validated route; malformed output is handled by the caller."""

        # Redact inside this boundary as a second line of defence. Callers may only
        # pass redacted text today, but this prevents a future caller leaking PII.
        safe_message = redact_pii(message).text[:1200]
        metadata = {
            "model": self.settings.FPT_LLM_MODEL,
            "max_tokens": self.max_tokens,
            "content_captured": False,
        }
        with start_observation(
            "hera.routing.model_assessment",
            settings=self.settings,
            as_type="generation",
            metadata=metadata,
        ) as observation:
            try:
                response = await asyncio.wait_for(
                    self.llm_client.generate(
                        [
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            {"role": "user", "content": safe_message},
                        ],
                        temperature=0.0,
                        max_tokens=self.max_tokens,
                    ),
                    timeout=self.timeout_seconds,
                )
                assessment = self._parse(response)
            except Exception as exc:
                observation.update(
                    metadata={
                        **metadata,
                        "decision_source": "deterministic_fallback",
                        "outcome": "error",
                        "error_type": exc.__class__.__name__,
                    }
                )
                raise

            observation.update(
                metadata={
                    **metadata,
                    "decision_source": (
                        "model"
                        if assessment.emergency.is_emergency
                        or assessment.classification is not None
                        else "deterministic_fallback"
                    ),
                    "outcome": "success",
                    "emergency": assessment.emergency.is_emergency,
                    "emergency_confidence": assessment.emergency_confidence,
                    "intent": (
                        assessment.classification.intent.value
                        if assessment.classification is not None
                        else "low_confidence"
                    ),
                    "intent_confidence": assessment.intent_confidence,
                }
            )
            return assessment

    def _parse(self, response: str) -> ModelRoutingAssessment:
        payload = _parse_json_object(response)
        emergency_confidence = _coerce_confidence(payload.get("emergency_confidence"))
        intent_confidence = _coerce_confidence(payload.get("intent_confidence"))
        shared_reason = payload.get("reason")
        emergency_reasons = _bounded_reasons(
            payload.get("emergency_reasons") or shared_reason
        )
        intent_reasons = _bounded_reasons(
            payload.get("intent_reasons") or shared_reason
        )

        raw_intent = str(payload.get("intent", "")).strip()
        try:
            intent = HospitalIntent(raw_intent)
        except ValueError:
            intent = None

        emergency_flag = _coerce_bool(payload.get("emergency"))
        if intent is HospitalIntent.EMERGENCY:
            emergency_flag = True
            emergency_confidence = max(emergency_confidence, intent_confidence)
        is_emergency = (
            emergency_flag
            and emergency_confidence >= self.emergency_confidence_threshold
        )
        emergency = EmergencyAssessment(
            is_emergency=is_emergency,
            confidence=emergency_confidence,
            matched_terms=(
                [f"model:{reason}" for reason in emergency_reasons]
                if is_emergency
                else []
            ),
        )

        classification = None
        if (
            intent is not None
            and not (intent is HospitalIntent.EMERGENCY and not is_emergency)
            and intent_confidence >= self.intent_confidence_threshold
        ):
            classification = IntentClassification(
                intent=intent,
                confidence=intent_confidence,
                reasons=[f"model:{reason}" for reason in intent_reasons]
                or ["model:routing"],
            )
        return ModelRoutingAssessment(
            emergency=emergency,
            classification=classification,
            emergency_confidence=emergency_confidence,
            intent_confidence=intent_confidence,
        )


_SYSTEM_PROMPT = """You are the routing classifier for a Vietnamese hospital assistant.
Classify the message only; do not answer it and do not provide medical advice.
Return exactly one compact JSON object on one line, without markdown or explanation:
{"emergency":boolean,"emergency_confidence":number,"intent":string,"intent_confidence":number,"reason":string}.
The intent must be exactly one of:
greeting, thanks, other_official, booking, schedule, service_price_current,
bhyt_household_contribution, insurance_general, bhyt_personal_benefit,
price_bhyt_calculation, procedure, working_hours, hospital_contact,
doctor_department, admission, follow_up, specialized_service, emergency,
human_handoff, general_support, unsupported.
Use schedule only for roster/availability questions such as which doctor works on a
date, at which facility, department, session or clinic room. A mention of "giờ khám"
alone does not make a message schedule. Use booking for appointment creation,
appointment validity, how far in advance to book, or how early to arrive. Use
procedure for administrative steps and documents. Use service_price_current only
for technical-service prices. Use bhyt_household_contribution only for household
contribution levels. Examples: "Tôi cần đến sớm trước giờ khám bao lâu?" -> booking;
"Bác sĩ nào khám sáng thứ Hai?" -> schedule; "Cần mang giấy tờ gì?" -> procedure.
Mark emergency true for plausible urgent symptoms or an explicit emergency request.
Confidence must be between 0 and 1. Reason must be one short category label, never
copied PII. Do not output any keys other than the five keys in the schema.
"""


def _parse_json_object(value: str) -> dict:
    decoder = json.JSONDecoder()
    candidate: dict | None = None
    cursor = 0
    while True:
        start = value.find("{", cursor)
        if start < 0:
            break
        try:
            parsed, _ = decoder.raw_decode(value[start:])
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        if isinstance(parsed, dict):
            candidate = parsed
        cursor = start + 1
    if candidate is None:
        raise ValueError("model routing classifier returned no valid JSON object")
    return candidate


def _coerce_confidence(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, numeric))


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return False


def _bounded_reasons(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [
        str(item).strip()[:80]
        for item in value
        if isinstance(item, str) and item.strip()
    ][:5]
