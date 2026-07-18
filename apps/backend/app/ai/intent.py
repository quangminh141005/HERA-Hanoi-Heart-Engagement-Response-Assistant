"""Intent classification for HERA chat routing."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum

from app.ai.emergency.detector import EmergencyDetector


class HospitalIntent(str, Enum):
    """High-level intents supported by the HERA assistant."""

    GREETING = "greeting"
    THANKS = "thanks"
    HOSPITAL_QA = "other_official"
    APPOINTMENT = "booking"
    DOCTOR_SCHEDULE = "schedule"
    SERVICE_PRICE = "service_price_current"
    INSURANCE = "bhyt_household_contribution"
    INSURANCE_GENERAL = "insurance_general"
    INSURANCE_PERSONAL_BENEFIT = "bhyt_personal_benefit"
    PRICE_BHYT_CALCULATION = "price_bhyt_calculation"
    PROCEDURE = "procedure"
    WORKING_HOURS = "working_hours"
    HOSPITAL_CONTACT = "hospital_contact"
    DOCTOR_DEPARTMENT = "doctor_department"
    ADMISSION = "admission"
    FOLLOW_UP = "follow_up"
    SPECIALIZED_SERVICE = "specialized_service"
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
            HospitalIntent.INSURANCE_GENERAL,
            HospitalIntent.PROCEDURE,
            HospitalIntent.WORKING_HOURS,
            HospitalIntent.HOSPITAL_CONTACT,
            HospitalIntent.ADMISSION,
            HospitalIntent.FOLLOW_UP,
            HospitalIntent.SPECIALIZED_SERVICE,
        }

class IntentClassifier:
    """Small deterministic classifier until a trained model is introduced."""

    def __init__(self, emergency_detector: EmergencyDetector | None = None):
        self.emergency_detector = emergency_detector or EmergencyDetector()

    def classify(self, message: str) -> IntentClassification:
        """Classify a user message for routing."""

        normalized = _normalize(message)
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
        if _contains_any(normalized, _INSURANCE_TERMS) and _contains_any(
            normalized, _PRICE_BHYT_CALCULATION_TERMS
        ):
            return IntentClassification(
                HospitalIntent.PRICE_BHYT_CALCULATION,
                0.95,
                ["unsupported price and BHYT calculation"],
            )
        if _contains_any(normalized, _INSURANCE_TERMS) and _contains_any(
            normalized, _PERSONAL_BENEFIT_TERMS
        ):
            return IntentClassification(
                HospitalIntent.INSURANCE_PERSONAL_BENEFIT,
                0.9,
                ["personal BHYT benefit keyword"],
            )
        if _contains_any(normalized, _DOCTOR_SCHEDULE_TERMS):
            return IntentClassification(
                HospitalIntent.DOCTOR_SCHEDULE,
                0.8,
                ["doctor schedule keyword"],
            )
        if _contains_any(normalized, _INSURANCE_TERMS) and _contains_any(
            normalized, _HOUSEHOLD_CONTRIBUTION_TERMS
        ):
            return IntentClassification(
                HospitalIntent.INSURANCE,
                0.9,
                ["household contribution keyword"],
            )
        if _contains_any(normalized, _PRICE_TERMS):
            return IntentClassification(
                HospitalIntent.SERVICE_PRICE,
                0.75,
                ["price keyword"],
            )
        if _contains_any(normalized, _WORKING_HOURS_TERMS):
            return IntentClassification(
                HospitalIntent.WORKING_HOURS,
                0.85,
                ["working-hours keyword"],
            )
        if _contains_any(normalized, _HOSPITAL_CONTACT_TERMS):
            return IntentClassification(
                HospitalIntent.HOSPITAL_CONTACT,
                0.85,
                ["hospital-contact keyword"],
            )
        if _contains_any(normalized, _PROCEDURE_TERMS):
            return IntentClassification(
                HospitalIntent.PROCEDURE,
                0.8,
                ["procedure keyword"],
            )
        if _contains_any(normalized, _ADMISSION_TERMS):
            return IntentClassification(
                HospitalIntent.ADMISSION,
                0.8,
                ["admission keyword"],
            )
        if _contains_any(normalized, _FOLLOW_UP_TERMS):
            return IntentClassification(
                HospitalIntent.FOLLOW_UP,
                0.8,
                ["follow-up keyword"],
            )
        if _contains_any(normalized, _SPECIALIZED_SERVICE_TERMS):
            return IntentClassification(
                HospitalIntent.SPECIALIZED_SERVICE,
                0.8,
                ["specialized-service keyword"],
            )
        if _contains_any(normalized, _INSURANCE_TERMS):
            return IntentClassification(
                HospitalIntent.INSURANCE_GENERAL,
                0.8,
                ["general insurance keyword"],
            )
        if _contains_any(normalized, _APPOINTMENT_TERMS):
            return IntentClassification(
                HospitalIntent.APPOINTMENT,
                0.8,
                ["appointment keyword"],
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
    return any(re.search(pattern, text) for pattern in terms)


def _normalize(text: str) -> str:
    lowered = text.strip().lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return without_marks.replace("đ", "d")


_GREETING_TERMS = (r"\bxin chao\b", r"\bhello\b", r"^hi\b", r"\bchao\b")
_THANKS_TERMS = (r"\bcam on\b", r"\bthank",)
_HANDOFF_TERMS = (
    r"\bgap nhan vien\b",
    r"\bchuyen nhan vien\b",
    r"\bnoi chuyen voi nguoi\b",
)
_APPOINTMENT_TERMS = (
    r"\bdat lich\b",
    r"\bdat kham\b",
    r"\bdat hen\b",
    r"\blich kham\b",
    r"\bhen kham\b",
    r"\bgio hen\b",
    r"\bgui yeu cau.*(?:dat|hen|kham)\b",
    r"\blich.*(?:hieu luc|xac nhan|chac chan)\b",
)
_DOCTOR_SCHEDULE_TERMS = (
    r"\blich bac si\b",
    r"\bbac si nao\b",
    r"\bphong kham\b",
    r"\bkhoa\b",
)
_PRICE_TERMS = (r"\bgia\b", r"\bchi phi\b", r"\bvien phi\b")
_INSURANCE_TERMS = (r"\bbhyt\b", r"\bbao hiem\b", r"\binsurance\b")
_HOUSEHOLD_CONTRIBUTION_TERMS = (
    r"\bmuc dong\b",
    r"\bdong bao nhieu\b",
    r"\bho gia dinh\b",
    r"\bthanh vien thu\b",
)
_PERSONAL_BENEFIT_TERMS = (
    r"\bquyen loi\b",
    r"\bduoc huong\b",
    r"\bchi tra\b",
    r"\bthanh toan bao nhieu\b",
    r"\bbao nhieu phan tram\b",
    r"%",
)
_PRICE_BHYT_CALCULATION_TERMS = (
    r"\btru\b",
    r"\bhoa don\b",
    r"\btoi phai tra\b",
    r"\bdong chi tra\b",
    r"\bgia dich vu.*bhyt\b",
)
_HOSPITAL_QA_TERMS = (
    r"\bquy trinh\b",
    r"\bthu tuc\b",
    r"\btai kham\b",
    r"\bnhap vien\b",
    r"\bgio lam viec\b",
)
_WORKING_HOURS_TERMS = (
    r"\bkhung gio\b",
    r"\bgio lam viec\b",
    r"\bgio nao\b",
    r"\bchu nhat\b",
    r"\ble, tet\b",
)
_HOSPITAL_CONTACT_TERMS = (
    r"\bdia chi\b",
    r"\bco so [12].*o dau\b",
    r"\bso lien he\b",
    r"\bhotline\b",
)
_PROCEDURE_TERMS = (
    r"\bthu tuc\b",
    r"\bquy trinh\b",
    r"\bco mat truoc\b",
    r"\bden som\b",
)
_ADMISSION_TERMS = (r"\bnhap vien\b", r"\bnam vien\b")
_FOLLOW_UP_TERMS = (r"\btai kham\b", r"\bkham lai\b")
_SPECIALIZED_SERVICE_TERMS = (r"\bdich vu chuyen sau\b", r"\bky thuat cao\b")

