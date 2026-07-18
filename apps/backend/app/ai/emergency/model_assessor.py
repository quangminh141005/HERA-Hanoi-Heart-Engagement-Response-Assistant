"""Model-assisted emergency risk assessment."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from app.ai.emergency.detector import EmergencyAssessment
from app.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelEmergencyAssessor:
    """Ask the configured LLM to classify emergency risk with a tiny JSON output."""

    llm_client: LLMClient
    timeout_seconds: float
    max_tokens: int
    confidence_threshold: float

    async def assess(self, message: str) -> EmergencyAssessment:
        """Return model emergency assessment; raise only to caller fallback path."""

        response = await asyncio.wait_for(
            self.llm_client.generate(
                [
                    {
                        "role": "system",
                        "content": (
                            "Bạn là bộ phân loại an toàn y tế cho trợ lý bệnh viện. "
                            "Chỉ đánh giá liệu tin nhắn người dùng có mô tả tình huống "
                            "cần cấp cứu/khẩn cấp hay không. Không chẩn đoán, không tư vấn. "
                            "Trả về JSON hợp lệ đúng schema: "
                            '{"emergency":boolean,"confidence":number,"reasons":[string]}.'
                        ),
                    },
                    {
                        "role": "user",
                        "content": message[:1200],
                    },
                ],
                temperature=0.0,
                max_tokens=self.max_tokens,
            ),
            timeout=self.timeout_seconds,
        )
        payload = _parse_json_object(response)
        emergency = bool(payload.get("emergency"))
        confidence = _coerce_confidence(payload.get("confidence"))
        reasons = [
            str(item)[:80]
            for item in payload.get("reasons", [])
            if isinstance(item, str) and item.strip()
        ][:5]
        if emergency and confidence >= self.confidence_threshold:
            return EmergencyAssessment(
                True,
                confidence,
                [f"model:{reason}" for reason in reasons] or ["model:emergency"],
            )
        return EmergencyAssessment(False, confidence, [])


def _parse_json_object(value: str) -> dict:
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model emergency classifier returned no JSON object")
    parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model emergency classifier returned non-object JSON")
    return parsed


def _coerce_confidence(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, numeric))
