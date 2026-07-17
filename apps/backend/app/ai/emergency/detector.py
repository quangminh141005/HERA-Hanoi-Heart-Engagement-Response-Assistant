"""High-sensitivity emergency symptom detection.

This is not a clinical triage model. It is an early safety gate that should be
replaced or reviewed by hospital clinicians before production rollout.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmergencyAssessment:
    """Emergency detection result."""

    is_emergency: bool
    confidence: float
    matched_terms: list[str] = field(default_factory=list)


class EmergencyDetector:
    """Detect high-risk symptom language in Vietnamese or English."""

    def assess(self, text: str) -> EmergencyAssessment:
        """Return a conservative emergency assessment."""

        normalized = _normalize(text)
        matched = [
            label
            for label, patterns in _EMERGENCY_PATTERNS.items()
            if any(re.search(pattern, normalized) for pattern in patterns)
        ]
        if not matched:
            return EmergencyAssessment(False, 0.0, [])
        confidence = min(0.99, 0.72 + (0.08 * len(matched)))
        return EmergencyAssessment(True, confidence, matched)


def build_emergency_response(
    *,
    emergency_hotline: str,
    hospital_hotline: str = "",
) -> str:
    """Build a safe emergency response in Vietnamese."""

    contact = f" hoặc hotline bệnh viện {hospital_hotline}" if hospital_hotline else ""
    return (
        "Triệu chứng bạn mô tả có thể là tình huống khẩn cấp. "
        "HERA không chẩn đoán, kê thuốc hoặc hướng dẫn điều trị trong trường hợp này. "
        f"Hãy gọi cấp cứu {emergency_hotline}{contact}, hoặc đến cơ sở y tế "
        "gần nhất ngay. "
        "Nếu có hướng dẫn cấp cứu chính thức của Bệnh viện Tim Hà Nội, "
        "hệ thống cần hiển thị "
        "đúng nội dung đó tại đây."
    )


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    without_marks = without_marks.replace("đ", "d")
    return re.sub(r"\s+", " ", without_marks).strip()


_EMERGENCY_PATTERNS = {
    "severe_chest_pain": (
        r"\bdau nguc (du doi|rat nang|khong chiu noi|keo dai)\b",
        r"\bsevere chest pain\b",
        r"\bcrushing chest pain\b",
    ),
    "shortness_of_breath": (
        r"\bkho tho\b",
        r"\bnghet tho\b",
        r"\bshort(ness)? of breath\b",
        r"\bcan'?t breathe\b",
    ),
    "fainting_or_shock": (
        r"\bngat\b",
        r"\bchoang\b",
        r"\bxiu\b",
        r"\bfaint(ed|ing)?\b",
        r"\bcollapse(d)?\b",
    ),
    "cyanosis": (
        r"\btim tai\b",
        r"\bmoi tim\b",
        r"\bblue lips\b",
    ),
    "dangerous_palpitations": (
        r"\btim dap (bat thuong|nhanh|loạn|loan).*(met|kho chiu|dau nguc|kho tho)\b",
        r"\bpalpitation(s)?.*(chest pain|shortness|faint|dizzy)\b",
    ),
}
