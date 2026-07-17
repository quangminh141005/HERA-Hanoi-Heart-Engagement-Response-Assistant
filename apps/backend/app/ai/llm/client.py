"""LLM provider abstraction."""

from __future__ import annotations

from typing import Protocol

from app.core.config import Settings


class LLMClient(Protocol):
    """Minimal async chat-generation interface."""

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> str:
        """Generate one assistant response."""


class NoopLLMClient:
    """Deterministic placeholder used until a provider is configured."""

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> str:
        """Return a safe placeholder answer."""

        del messages, temperature, max_tokens
        return (
            "HERA chưa được cấu hình LLM và chỉ có thể trả lời từ các luồng an toàn "
            "hoặc dữ liệu chính thức đã được tích hợp."
        )


def build_llm_client(settings: Settings) -> LLMClient:
    """Build the configured LLM client.

    TODO: add concrete OpenAI, Gemini, and Anthropic adapters after provider
    selection, retry policy, and PHI logging rules are approved.
    """

    del settings
    return NoopLLMClient()

