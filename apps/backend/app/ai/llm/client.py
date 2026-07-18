"""LLM provider abstraction."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Protocol

from app.core.config import Settings
from app.observability.prometheus import record_upstream_failure

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
    """Deterministic safe fallback used when model generation is unavailable."""

    provider_name = "noop"

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> str:
        """Return a safe non-factual fallback answer."""

        del messages, temperature, max_tokens
        return (
            "HERA chưa được cấu hình LLM và chỉ có thể trả lời từ các luồng an toàn "
            "hoặc dữ liệu chính thức đã được tích hợp."
        )


    async def close(self) -> None:
        return None


class OpenAILLMClient:
    """OpenAI chat-completion adapter."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float = 8.0,
        provider_label: str = "openai_compatible",
        sdk_client: Any | None = None,
    ) -> None:
        self.model = model
        self.provider_label = provider_label
        if sdk_client is not None:
            self._client = sdk_client
            return

        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> str:
        """Generate a response with OpenAI."""

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            record_upstream_failure(self.provider_label, exc)
            raise
        content = _coerce_text(response.choices[0].message.content)
        if not content.strip():
            error = RuntimeError("OpenAI returned an empty response.")
            record_upstream_failure(self.provider_label, error)
            raise error
        return content.strip()

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result


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


    async def close(self) -> None:
        for client in self.clients:
            close = getattr(client, "close", None)
            if callable(close):
                result = close()
                if hasattr(result, "__await__"):
                    await result


class GuardedLLMClient:
    """Protect the upstream model from duplicate bursts and overload."""

    provider_name = "guarded"

    def __init__(
        self,
        client: LLMClient,
        *,
        max_concurrent_requests: int,
        queue_timeout_seconds: float,
        cache_enabled: bool,
        cache_ttl_seconds: int,
        cache_max_entries: int,
    ) -> None:
        self.client = client
        self._semaphore = asyncio.Semaphore(max_concurrent_requests)
        self._queue_timeout_seconds = queue_timeout_seconds
        self._cache_enabled = cache_enabled
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache_max_entries = cache_max_entries
        self._cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._in_flight: dict[str, asyncio.Task[str]] = {}
        self._lock = asyncio.Lock()
        self._safe_client = NoopLLMClient()

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> str:
        key = _cache_key(messages, temperature=temperature, max_tokens=max_tokens)
        if self._cache_enabled:
            cached = await self._get_cached(key)
            if cached is not None:
                return cached

        async with self._lock:
            existing = self._in_flight.get(key)
            if existing is None:
                existing = asyncio.create_task(
                    self._generate_uncached(
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                )
                self._in_flight[key] = existing

        try:
            result = await asyncio.shield(existing)
        finally:
            async with self._lock:
                if self._in_flight.get(key) is existing and existing.done():
                    self._in_flight.pop(key, None)

        if self._cache_enabled and _cacheable_response(result):
            await self._set_cached(key, result)
        return result

    async def _generate_uncached(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self._queue_timeout_seconds,
            )
        except TimeoutError:
            logger.warning(
                "llm queue timeout; returning safe fallback",
                extra={"event": "llm_queue_timeout"},
            )
            return await self._safe_client.generate(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        try:
            return await self.client.generate(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        finally:
            self._semaphore.release()

    async def _get_cached(self, key: str) -> str | None:
        now = time.monotonic()
        async with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                return None
            expires_at, value = cached
            if expires_at <= now:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return value

    async def _set_cached(self, key: str, value: str) -> None:
        expires_at = time.monotonic() + self._cache_ttl_seconds
        async with self._lock:
            self._cache[key] = (expires_at, value)
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_max_entries:
                self._cache.popitem(last=False)

    async def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result


def build_llm_client(settings: Settings) -> LLMClient:
    """Build the fixed FPT/OpenAI-compatible client with safe local degradation."""

    if settings.LLM_PROVIDER == "noop":
        return NoopLLMClient()
    client = _build_provider_client(settings.LLM_PROVIDER, settings)
    if client is None:
        return NoopLLMClient()
    fallback_client: LLMClient = FallbackLLMClient([client])
    return GuardedLLMClient(
        fallback_client,
        max_concurrent_requests=settings.LLM_MAX_CONCURRENT_REQUESTS,
        queue_timeout_seconds=settings.LLM_QUEUE_TIMEOUT_SECONDS,
        cache_enabled=settings.LLM_RESPONSE_CACHE_ENABLED,
        cache_ttl_seconds=settings.LLM_RESPONSE_CACHE_TTL_SECONDS,
        cache_max_entries=settings.LLM_RESPONSE_CACHE_MAX_ENTRIES,
    )


def _build_provider_client(provider: str, settings: Settings) -> LLMClient | None:
    if provider == "openai":
        use_fpt = bool(settings.API_KEY and settings.FPT_LLM_MODEL)
        api_key = settings.API_KEY if use_fpt else settings.OPENAI_API_KEY
        if not api_key:
            return None
        return OpenAILLMClient(
            api_key=api_key,
            model=(
                settings.FPT_LLM_MODEL
                if use_fpt
                else (settings.OPENAI_MODEL or settings.LLM_MODEL)
            ),
            base_url=(
                settings.FPT_API_BASE_URL if use_fpt else settings.OPENAI_BASE_URL
            ),
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            provider_label="fpt_llm" if use_fpt else "openai",
        )

    logger.warning(
        "llm provider is configured but no adapter is available",
        extra={"event": "llm_provider_unsupported", "llm_provider": provider},
    )
    return None

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


def _cache_key(
    messages: list[ChatMessage],
    *,
    temperature: float,
    max_tokens: int,
) -> str:
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _cacheable_response(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and not stripped.startswith("HERA chưa được cấu hình LLM")
