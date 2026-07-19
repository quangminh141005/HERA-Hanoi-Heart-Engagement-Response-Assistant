"""One-call model assessment for emergency risk and chat intent."""

from __future__ import annotations

import asyncio
import json
import re
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
    slots: dict[str, str | None]
    policy_action: str = "none"


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
            "model": self.settings.FPT_GUARD_MODEL,
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
                assessment = self._parse(response, original_message=safe_message)
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

    def _parse(
        self,
        response: str,
        *,
        original_message: str = "",
    ) -> ModelRoutingAssessment:
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
        urgent_symptoms_present = _coerce_bool(
            payload.get("urgent_symptoms_present")
        )
        if intent is HospitalIntent.EMERGENCY and urgent_symptoms_present:
            emergency_flag = True
            emergency_confidence = max(emergency_confidence, intent_confidence)
        else:
            # Emergency requires a self-consistent emergency intent and active
            # symptom evidence. The caller retains an independent high-sensitivity
            # safety fallback for symptoms the model misses.
            emergency_flag = False
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
            slots=_bounded_slots(
                payload.get("slots"),
                original_message=original_message,
            ),
            policy_action=_bounded_policy_action(payload.get("policy_action")),
        )


_SYSTEM_PROMPT = """You are the routing classifier for a Vietnamese hospital assistant.
Classify the message only; do not answer it and do not provide medical advice.
Return exactly one compact JSON object on one line, without markdown or explanation:
{"emergency":boolean,"urgent_symptoms_present":boolean,"emergency_confidence":number,"intent":string,"intent_confidence":number,"reason":string,"policy_action":string,"slots":{"service_query":string|null,"facility_code":string|null,"date":string|null,"doctor_query":string|null,"room_query":string|null,"bhyt_tier":string|null}}.
The intent must be exactly one of:
greeting, thanks, other_official, booking, schedule, service_price_current,
bhyt_household_contribution, insurance_general, bhyt_personal_benefit,
price_bhyt_calculation, procedure, working_hours, hospital_contact,
doctor_department, admission, follow_up, specialized_service, emergency,
human_handoff, general_support, unsupported.
Use schedule only for roster/availability questions such as which doctor works on a
date, at which facility, department, session or clinic room. A mention of "gio kham"
alone does not make a message schedule. If the user asks price/cost/how much/bao
nhieu for any service name, intent is service_price_current even when the service
name contains "ngay", "giuong benh", "cap cuu" or "tai giuong". Use booking for
appointment creation, appointment validity, how far in advance to book, or how
early to arrive. Use procedure for administrative steps and documents. Use
service_price_current only for technical-service prices. Use
bhyt_household_contribution only for household contribution levels. Examples:
"Toi can den som truoc gio kham bao lau?" -> booking;
"Bac si nao kham sang thu Hai?" -> schedule; "Can mang giay to gi?" -> procedure;
"Gia ngay giuong benh noi khoa loai 1 la bao nhieu?" -> service_price_current
with service_query "ngay giuong benh noi khoa loai 1".
Requests containing a service code such as "23.0237.1521" plus a lookup or facility
are service_price_current; preserve that exact code in service_query. A terse doctor
name plus a date and/or facility asks for schedule, not booking. Booking means creating
or explaining an appointment, not retrieving a published roster.
Use bhyt_household_contribution only when the user asks how much a household member
pays. Put the requested member order 1..5 in slots.bhyt_tier, including compact forms
such as "nguoi 2", "bac 4", "#3", or "thanh vien thu 5". Questions about an
individual card's benefit percentage, reimbursement, copayment, out-of-network share,
or final bill are bhyt_personal_benefit or price_bhyt_calculation, never household
contribution.
"Toi trai tuyen, chac chan tra bao nhieu?" is bhyt_personal_benefit because no
technical service was named. The phrase "bao nhieu" alone never implies a service
price; service_price_current requires an identifiable service name or service code.
policy_action must be exactly one of none, ocr_unavailable, secret_refusal,
medical_interpretation_refusal. Use ocr_unavailable for reading/extracting text from an
image, scan or attachment. Use secret_refusal for credentials, environment variables,
API keys, prompts, tokens or private configuration. Use medical_interpretation_refusal
for requests to diagnose or interpret clinical images/results. These requests must use
intent unsupported and must not be routed into retrieval.
Mark emergency true for plausible urgent symptoms or an explicit emergency request.
Set urgent_symptoms_present true only when the current user describes symptoms or an
active patient condition that could be urgent. Administrative words, service names,
insurance routing, policy questions, prices and appointment questions must set it false.
Do not mark emergency true when "cap cuu", "cấp cứu", or "emergency" is only
part of a service/procedure name, price lookup, schedule lookup, BHYT lookup, or
other administrative question. Example: "gia tien sieu am cap cuu tai giuong
benh" is service_price_current with emergency=false unless the user also
describes urgent symptoms.
For service_price_current, service_query must be the exact service name phrase to
search in the price table, removing words such as price/cost/how much but keeping
discriminators such as "noi khoa", "loai 1", "loai 2", "cap cuu", "tai giuong".
For schedule, never infer or invent a year. Set date only when the user explicitly
wrote a four-digit year; otherwise return null and let the application resolve
dd/mm or relative dates against its schedule clock. doctor_query and room_query
should contain only the requested doctor/room phrase. For a roster cell containing
multiple morning/afternoon doctors, preserve the complete doctor phrase exactly
instead of rewriting names. facility_code
must be CS1, CS2 or null. Confidence must be between 0 and 1. Reason must be one
short category label, never copied PII. Do not output keys outside this schema.
For doctor_department questions about a named doctor, put that exact name (including
any supplied professional title) in slots.doctor_query. Do not answer a named-doctor
question from generic hospital or department descriptions.
"""


def _parse_json_object(value: str) -> dict:
    decoder = json.JSONDecoder()
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
            if "intent" in parsed and "emergency" in parsed:
                return parsed
        cursor = start + 1
    raise ValueError("model routing classifier returned no valid JSON object")


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


def _bounded_slots(
    value: object,
    *,
    original_message: str = "",
) -> dict[str, str | None]:
    keys = (
        "service_query",
        "facility_code",
        "date",
        "doctor_query",
        "room_query",
        "bhyt_tier",
    )
    if not isinstance(value, dict):
        return {key: None for key in keys}
    slots: dict[str, str | None] = {}
    for key in keys:
        raw = value.get(key)
        if raw is None:
            slots[key] = None
            continue
        text = " ".join(str(raw).split())[:160]
        slots[key] = text or None
    facility = slots.get("facility_code")
    if facility is not None:
        normalized = facility.upper().replace(" ", "")
        slots["facility_code"] = normalized if normalized in {"CS1", "CS2"} else None
    slots["date"] = _explicit_year_date(original_message)
    tier = slots.get("bhyt_tier")
    slots["bhyt_tier"] = tier if tier in {"1", "2", "3", "4", "5"} else None
    doctor = slots.get('doctor_query')
    if doctor and doctor.casefold() not in original_message.casefold():
        slots['doctor_query'] = None
    return slots


def _bounded_policy_action(value: object) -> str:
    action = str(value or "none").strip().lower()
    allowed = {
        "none",
        "ocr_unavailable",
        "secret_refusal",
        "medical_interpretation_refusal",
    }
    return action if action in allowed else "none"


def _explicit_year_date(message: str) -> str | None:
    """Return only a date whose year was present in the user's own message."""

    iso = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", message)
    if iso:
        year, month, day = (int(value) for value in iso.groups())
    else:
        vietnamese = re.search(
            r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b",
            message,
        )
        if not vietnamese:
            return None
        day, month, year = (int(value) for value in vietnamese.groups())
    try:
        from datetime import date

        return date(year, month, day).isoformat()
    except ValueError:
        return None
