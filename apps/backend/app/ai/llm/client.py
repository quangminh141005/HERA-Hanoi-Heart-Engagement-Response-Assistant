"""LLM provider abstraction."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)

ChatMessage = dict[str, str]


class LLMClient(Protocol):
    """Minimal async chat-generation interface."""

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> str:
        """Generate one assistant response."""


class NoopLLMClient:
    """Deterministic placeholder used until a provider is configured."""

    provider_name = "noop"

    async def generate(
        self,
        messages: list[ChatMessage],
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


class OpenAILLMClient:
    """OpenAI or OpenAI-compatible chat-completion adapter."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        provider_name: str = "openai",
        sdk_client: Any | None = None,
    ) -> None:
        self.model = model
        self.provider_name = provider_name
        if sdk_client is not None:
            self._client = sdk_client
            return

        from openai import AsyncOpenAI

        if base_url:
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = AsyncOpenAI(api_key=api_key)

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> str:
        """Generate a response with OpenAI."""

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = _coerce_text(response.choices[0].message.content)
        if not content.strip():
            raise RuntimeError("OpenAI returned an empty response.")
        return content.strip()


class GeminiLLMClient:
    """Gemini adapter used as the fallback LLM."""

    provider_name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        sdk_model: Any | None = None,
    ) -> None:
        self.model = model
        if sdk_model is not None:
            self._model = sdk_model
            return

        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> str:
        """Generate a response with Gemini."""

        prompt = _messages_to_prompt(messages)
        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if hasattr(self._model, "generate_content_async"):
            response = await self._model.generate_content_async(
                prompt,
                generation_config=generation_config,
            )
        else:
            response = await asyncio.to_thread(
                self._model.generate_content,
                prompt,
                generation_config=generation_config,
            )

        content = _extract_gemini_text(response)
        if not content.strip():
            raise RuntimeError("Gemini returned an empty response.")
        return content.strip()


class FallbackLLMClient:
    """Try configured providers in order and degrade safely if all fail."""

    provider_name = "fallback"

    def __init__(self, clients: list[LLMClient]) -> None:
        if not clients:
            raise ValueError("FallbackLLMClient requires at least one client.")
        self.clients = clients
        self._safe_client = NoopLLMClient()

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> str:
        """Generate with the first available provider."""

        failed_providers: list[str] = []
        for client in self.clients:
            provider = getattr(client, "provider_name", client.__class__.__name__)
            try:
                return await client.generate(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                failed_providers.append(provider)
                logger.warning(
                    "llm provider failed; trying next fallback",
                    extra={
                        "event": "llm_provider_failed",
                        "llm_provider": provider,
                        "error_type": exc.__class__.__name__,
                    },
                )

        logger.error(
            "all configured llm providers failed",
            extra={
                "event": "llm_all_providers_failed",
                "llm_providers": failed_providers,
            },
        )
        return await self._safe_client.generate(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )


def build_llm_client(settings: Settings) -> LLMClient:
    """Build the configured LLM client.

    FPT Cloud is exposed as an OpenAI-compatible provider and uses OPEN_API_KEY.
    Gemini can be configured as a fallback with GEMINI_API_KEY.
    """

    clients: list[LLMClient] = []
    for provider in _provider_order(settings):
        client = _build_provider_client(provider, settings)
        if client is not None:
            clients.append(client)

    if not clients:
        return NoopLLMClient()
    if len(clients) == 1:
        return clients[0]
    return FallbackLLMClient(clients)


def _provider_order(settings: Settings) -> list[str]:
    providers: list[str] = []
    for provider in (settings.LLM_PROVIDER, settings.LLM_FALLBACK_PROVIDER):
        if provider in {"none", "noop"}:
            continue
        if provider not in providers:
            providers.append(provider)
    return providers


def _build_provider_client(provider: str, settings: Settings) -> LLMClient | None:
    if provider == "fpt":
        if not settings.OPEN_API_KEY:
            return None
        return OpenAILLMClient(
            api_key=settings.OPEN_API_KEY,
            base_url=settings.OPEN_API_BASE_URL,
            model=settings.LLM_MODEL,
            provider_name="fpt",
        )

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            return None
        return OpenAILLMClient(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
        )

    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            return None
        return GeminiLLMClient(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
        )

    logger.warning(
        "llm provider is configured but no adapter is available",
        extra={"event": "llm_provider_unsupported", "llm_provider": provider},
    )
    return None


def _messages_to_prompt(messages: list[ChatMessage]) -> str:
    role_labels = {
        "system": "System",
        "user": "User",
        "assistant": "Assistant",
    }
    prompt_parts: list[str] = []
    for message in messages:
        role = role_labels.get(message.get("role", ""), "Message")
        prompt_parts.append(f"{role}:\n{message.get('content', '')}")
    return "\n\n".join(prompt_parts)


def _coerce_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
            else:
                text = getattr(item, "text", None)
            if text:
                parts.append(str(text))
        return "\n".join(parts)
    return str(content)


def _extract_gemini_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text)

    parts: list[str] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                parts.append(str(part_text))
    return "\n".join(parts)
