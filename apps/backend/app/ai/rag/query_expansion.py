"""Model-assisted query expansion for approved-fact RAG retrieval."""

from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from app.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)


class QueryExpander(Protocol):
    async def expand(self, query: str) -> str | None:
        """Return one safe retrieval expansion, or None when expansion is unsafe."""


class NoopQueryExpander:
    async def expand(self, query: str) -> None:
        del query
        return None


class HydeQueryExpander:
    """Use a small LLM to create a compact hypothetical retrieval document."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        max_tokens: int,
        max_chars: int,
    ) -> None:
        self.llm_client = llm_client
        self.max_tokens = max_tokens
        self.max_chars = max_chars

    async def expand(self, query: str) -> str | None:
        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn tạo query mở rộng cho retrieval nội bộ của chatbot bệnh viện. "
                    "Không trả lời người dùng. Không bịa giá, lịch, tên bác sĩ, URL, "
                    "số điện thoại hoặc chính sách. Chỉ viết lại nhu cầu thành các "
                    "cụm tìm kiếm ngắn, đồng nghĩa, không quá 60 từ. Trả JSON: "
                    "{\"expanded_query\":\"...\"}."
                ),
            },
            {"role": "user", "content": query},
        ]
        try:
            raw = await self.llm_client.generate(
                messages,
                temperature=0.0,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            logger.warning(
                "hyde query expansion failed; using original query",
                extra={
                    "event": "hyde_query_expansion_failed",
                    "error_type": exc.__class__.__name__,
                },
            )
            return None
        expanded = _parse_expanded_query(raw)
        if expanded is None:
            return None
        expanded = " ".join(expanded.split())[: self.max_chars]
        if _looks_like_answer_or_secret(expanded):
            return None
        return expanded if expanded and expanded.casefold() != query.casefold() else None


def _parse_expanded_query(raw: str) -> str | None:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            value = payload.get("expanded_query")
            if isinstance(value, str):
                return value
    cleaned = raw.strip().strip("`")
    return cleaned or None


def _looks_like_answer_or_secret(value: str) -> bool:
    folded = value.casefold()
    forbidden = (
        " vnd",
        "₫",
        "api_key",
        "sk-",
        "http://",
        "https://",
        "gọi 115",
        "chan doan",
        "chẩn đoán",
    )
    return any(token in folded for token in forbidden)
