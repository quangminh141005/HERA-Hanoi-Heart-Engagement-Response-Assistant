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
        matched = []
        for label, patterns in _EMERGENCY_PATTERNS.items():
            if any(_has_non_negated_match(pattern, normalized) for pattern in patterns):
                matched.append(label)
        if _is_admin_or_service_lookup(normalized) and not _has_direct_symptom_context(
            matched,
            normalized,
        ):
            return EmergencyAssessment(False, 0.0, [])
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
        "hệ thống cần hiển thị đúng nội dung đó tại đây."
    )


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    without_marks = without_marks.replace("đ", "d")
    return re.sub(r"\s+", " ", without_marks).strip()


def _has_non_negated_match(pattern: str, text: str) -> bool:
    for match in re.finditer(pattern, text):
        prefix = text[max(0, match.start() - 40) : match.start()]
        if re.search(
            r"\b(?:khong|chua|het|khong con)(?:\s+[a-z]+){0,3}\s+$",
            prefix,
        ):
            continue
        return True
    return False


def _is_admin_or_service_lookup(text: str) -> bool:
    """Return true when emergency wording is likely part of a lookup target."""

    lookup_patterns = (
        r"\b(gia|gia tien|bao nhieu|chi phi|muc gia|bang gia|don gia|phi)\b",
        r"\b(dich vu|ky thuat|thu thuat|xet nghiem|sieu am|noi soi|chup|phau thuat)\b",
        r"\b(ma dich vu|ma tuong duong|bhyt|bao hiem)\b",
        r"\b(lich|ca kham|bac si|dat lich|booking)\b",
        r"\b(price|cost|fee|service|procedure|schedule|appointment)\b",
    )
    return any(re.search(pattern, text) for pattern in lookup_patterns)


def _has_direct_symptom_context(matched: list[str], text: str) -> bool:
    """Keep true symptom emergencies, suppress emergency words inside service names."""

    direct_symptom_labels = {
        "severe_chest_pain",
        "shortness_of_breath",
        "fainting_or_shock",
        "cyanosis",
        "dangerous_palpitations",
    }
    if direct_symptom_labels.intersection(matched):
        return True
    if "suspected_heart_attack_or_stroke" not in matched:
        return False
    return bool(
        re.search(
            r"\b(hien tai|bay gio|vua|dang|nguoi nha|benh nhan|ba toi|me toi|toi nghi)\b",
            text,
        )
    )


_EMERGENCY_PATTERNS = {
    "explicit_emergency_request": (
        r"\b(cap cuu|khan cap|nguy cap|nguy kich|goi 115|goi cap cuu)\b",
        r"\b(emergency|urgent|critical condition)\b",
    ),
    "severe_chest_pain": (
        r"\bdau nguc\b.*\b(kho tho|ngat|choang|xiu|vung tim|lan ra tay|lan ra vai|lan ra ham)\b",
        r"\bdau nguc (du doi|rat nang|khong chiu noi|keo dai|that chat|de nang)\b",
        r"\bsevere chest pain\b",
        r"\bcrushing chest pain\b",
    ),
    "shortness_of_breath": (
        r"\bkho tho\b",
        r"\bnghet tho\b",
        r"\btho gap\b",
        r"\bkhong tho duoc\b",
        r"\bshort(ness)? of breath\b",
        r"\bcan'?t breathe\b",
    ),
    "fainting_or_shock": (
        r"\bngat\b",
        r"\bchoang\b",
        r"\bxiu\b",
        r"\bmat y thuc\b",
        r"\bli bi\b",
        r"\bsoc\b",
        r"\bfaint(ed|ing)?\b",
        r"\bcollapse(d)?\b",
    ),
    "cyanosis": (
        r"\b(?:benh nhan|nguoi benh|da|mat|moi|tay|chan)\s+tim\s+tai\b",
        r"\btim\s+tai\s+(?:toan than|mat|moi|tay|chan)\b",
        r"\bmoi\s+tim\b",
        r"\bblue lips\b",
    ),
    "dangerous_palpitations": (
        r"\btim dap (bat thuong|nhanh|loan).*(met|kho chiu|dau nguc|kho tho)\b",
        r"\bhoi hop trong nguc\b.*\b(kho tho|dau nguc|choang|ngat|xiu)\b",
        r"\bpalpitation(s)?.*(chest pain|shortness|faint|dizzy)\b",
    ),
    "suspected_heart_attack_or_stroke": (
        r"\b(nhoi mau co tim|dau tim|ngung tim|tim ngung dap)\b",
        r"\b(dot quy|tai bien mach mau nao|meo mieng|yeu liet nua nguoi|noi kho)\b",
        r"\b(heart attack|cardiac arrest|stroke)\b",
    ),
}
