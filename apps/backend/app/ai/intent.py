"""Intent classification for HERA chat routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.ai.emergency.detector import EmergencyDetector


class HospitalIntent(str, Enum):
    """High-level intents supported by the HERA assistant."""

    GREETING = "greeting"
    THANKS = "thanks"
    HOSPITAL_QA = "hospital_qa"
    APPOINTMENT = "appointment"
    DOCTOR_SCHEDULE = "doctor_schedule"
    SERVICE_PRICE = "service_price"
    INSURANCE = "insurance"
    EMERGENCY = "emergency"
    HUMAN_HANDOFF = "human_handoff"
    GENERAL_SUPPORT = "general_support"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class IntentClassification:
    """Intent classification with routing hints."""

    intent: HospitalIntent
    confidence: float
    reasons: list[str] = field(default_factory=list)

    @property
    def requires_rag(self) -> bool:
        return self.intent in {
            HospitalIntent.HOSPITAL_QA,
            HospitalIntent.INSURANCE,
            HospitalIntent.SERVICE_PRICE,
        }

    @property
    def requires_hospital_api(self) -> bool:
        return self.intent in {
            HospitalIntent.APPOINTMENT,
            HospitalIntent.DOCTOR_SCHEDULE,
            HospitalIntent.SERVICE_PRICE,
        }


class IntentClassifier:
    """Small deterministic classifier until a trained model is introduced."""

    def __init__(self, emergency_detector: EmergencyDetector | None = None):
        self.emergency_detector = emergency_detector or EmergencyDetector()

    def classify(self, message: str) -> IntentClassification:
        """Classify a user message for routing."""

        normalized = message.strip().lower()
        emergency = self.emergency_detector.assess(message)
        if emergency.is_emergency:
            return IntentClassification(
                intent=HospitalIntent.EMERGENCY,
                confidence=emergency.confidence,
                reasons=emergency.matched_terms,
            )
        if _contains_any(normalized, _GREETING_TERMS):
            return IntentClassification(HospitalIntent.GREETING, 0.95, ["greeting"])
        if _contains_any(normalized, _THANKS_TERMS):
            return IntentClassification(HospitalIntent.THANKS, 0.95, ["thanks"])
        if _contains_any(normalized, _HANDOFF_TERMS):
            return IntentClassification(
                HospitalIntent.HUMAN_HANDOFF,
                0.85,
                ["handoff keyword"],
            )
        if _contains_any(normalized, _APPOINTMENT_TERMS):
            return IntentClassification(
                HospitalIntent.APPOINTMENT,
                0.8,
                ["appointment keyword"],
            )
        if _contains_any(normalized, _DOCTOR_SCHEDULE_TERMS):
            return IntentClassification(
                HospitalIntent.DOCTOR_SCHEDULE,
                0.8,
                ["doctor schedule keyword"],
            )
        if _contains_any(normalized, _PRICE_TERMS):
            return IntentClassification(
                HospitalIntent.SERVICE_PRICE,
                0.75,
                ["price keyword"],
            )
        if _contains_any(normalized, _INSURANCE_TERMS):
            return IntentClassification(
                HospitalIntent.INSURANCE,
                0.8,
                ["insurance keyword"],
            )
        if _contains_any(normalized, _HOSPITAL_QA_TERMS):
            return IntentClassification(
                HospitalIntent.HOSPITAL_QA,
                0.75,
                ["hospital knowledge keyword"],
            )
        return IntentClassification(
            HospitalIntent.GENERAL_SUPPORT,
            0.55,
            ["default support route"],
        )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


_GREETING_TERMS = ("xin chao", "xin chào", "hello", "hi", "chào")
_THANKS_TERMS = ("cam on", "cảm ơn", "cám ơn", "thank")
_HANDOFF_TERMS = ("nhan vien", "nhân viên", "tong dai", "tổng đài", "hotline")
_APPOINTMENT_TERMS = (
    "dat lich",
    "đặt lịch",
    "lich kham",
    "lịch khám",
    "hen kham",
    "hẹn khám",
)
_DOCTOR_SCHEDULE_TERMS = (
    "lich bac si",
    "lịch bác sĩ",
    "bac si nao",
    "bác sĩ nào",
    "khoa",
    "phong kham",
    "phòng khám",
)
_PRICE_TERMS = ("gia", "giá", "chi phi", "chi phí", "vien phi", "viện phí")
_INSURANCE_TERMS = ("bhyt", "bảo hiểm", "bao hiem", "insurance")
_HOSPITAL_QA_TERMS = (
    "quy trinh",
    "quy trình",
    "thu tuc",
    "thủ tục",
    "tai kham",
    "tái khám",
    "nhap vien",
    "nhập viện",
    "gio lam viec",
    "giờ làm việc",
)

