"""LLM provider abstraction."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections import OrderedDict
from typing import Any, Protocol

from app.ai.observability.tracing import start_observation
from app.ai.providers.retry import retry_provider_call
from app.core.config import Settings
from app.observability.ai_usage import extract_openai_usage
from app.observability.prometheus import record_ai_usage, record_upstream_failure

logger = logging.getLogger(__name__)

ChatMessage = dict[str, str]
SAFE_LLM_FALLBACK_MESSAGE = (
    "HERA ch\u01b0a \u0111\u01b0\u1ee3c c\u1ea5u h\u00ecnh LLM v\u00e0 "
    "ch\u1ec9 c\u00f3 th\u1ec3 tr\u1ea3 l\u1eddi t\u1eeb c\u00e1c lu\u1ed3ng "
    "an to\u00e0n ho\u1eb7c d\u1eef li\u1ec7u ch\u00ednh th\u1ee9c "
    "\u0111\u00e3 \u0111\u01b0\u1ee3c t\u00edch h\u1ee3p."
)
SAFE_LLM_FALLBACK_PREFIX = (
    "HERA ch\u01b0a \u0111\u01b0\u1ee3c c\u1ea5u h\u00ecnh LLM"
)


class LLMClient(Protocol):
    """Minimal async chat-generation interface."""

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
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
        max_tokens: int = 1024,
    ) -> str:
        """Return a safe non-factual fallback answer."""

        del messages, temperature, max_tokens
        return SAFE_LLM_FALLBACK_MESSAGE

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
        settings: Settings | None = None,
        retry_max_attempts: int = 1,
        retry_base_delay_seconds: float = 0.25,
        retry_max_delay_seconds: float = 2.0,
    ) -> None:
        self.model = model
        self.provider_label = provider_label
        self.settings = settings
        self.retry_max_attempts = retry_max_attempts
        self.retry_base_delay_seconds = retry_base_delay_seconds
        self.retry_max_delay_seconds = retry_max_delay_seconds
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
        max_tokens: int = 1024,
    ) -> str:
        """Generate a response with OpenAI."""

        if self.settings is None:
            return await self._generate_provider_response(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                observation=None,
            )

        trace_kwargs = {
            "model": self.model,
            "model_parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        }
        if self.settings.LANGFUSE_CAPTURE_CONTENT:
            trace_kwargs["input"] = messages
        with start_observation(
            "hera.llm.provider_call",
            settings=self.settings,
            as_type="generation",
            metadata={
                "provider": self.provider_label,
                "model": self.model,
                "max_tokens": max_tokens,
                "content_capture": self.settings.LANGFUSE_CAPTURE_CONTENT,
                "streaming": False,
                "ttft_available": False,
            },
            **trace_kwargs,
        ) as observation:
            try:
                result = await self._generate_provider_response(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    observation=observation,
                )
            except Exception as exc:
                observation.update(
                    metadata={
                        "result": "error",
                        "error_type": exc.__class__.__name__,
                    }
                )
                raise
            observation.update(metadata={"result": "success"})
            return result

    async def _generate_provider_response(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        observation: Any | None,
    ) -> str:
        try:
            response = await retry_provider_call(
                lambda: self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                label=self.provider_label,
                max_attempts=self.retry_max_attempts,
                base_delay_seconds=self.retry_base_delay_seconds,
                max_delay_seconds=self.retry_max_delay_seconds,
                retry_timeouts=False,
            )
        except Exception as exc:
            record_upstream_failure(self.provider_label, exc)
            raise
        usage = extract_openai_usage(response)
        record_ai_usage(
            self.provider_label,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        content = _coerce_text(response.choices[0].message.content)
        if observation is not None:
            trace_update = {
                "metadata": {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                },
                "usage_details": _langfuse_usage_details(usage),
            }
            if self.settings is not None and self.settings.LANGFUSE_CAPTURE_CONTENT:
                trace_update["output"] = content.strip()
            observation.update(**trace_update)
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
        max_tokens: int = 1024,
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
        settings: Settings | None = None,
        distributed_gate: RedisModelConcurrencyGate | None = None,
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
        self.settings = settings
        self._distributed_gate = distributed_gate

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> str:
        key = _cache_key(messages, temperature=temperature, max_tokens=max_tokens)
        if self._cache_enabled:
            cached = await self._get_cached(key)
            if cached is not None:
                if self.settings is not None:
                    with start_observation(
                        "hera.llm.cache_hit",
                        settings=self.settings,
                        as_type="span",
                        metadata={
                            "cache": "process_memory",
                            "ttl_seconds": self._cache_ttl_seconds,
                        },
                    ):
                        pass
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
        lease_token: str | None = None
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
            if self._distributed_gate is not None:
                lease_token = await self._distributed_gate.acquire(
                    timeout_seconds=self._queue_timeout_seconds
                )
                if lease_token is None:
                    logger.warning(
                        "distributed model queue timeout; returning safe fallback",
                        extra={"event": "llm_distributed_queue_timeout"},
                    )
                    return await self._safe_client.generate(
                        messages, temperature=temperature, max_tokens=max_tokens
                    )
            return await self.client.generate(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        finally:
            if lease_token is not None and self._distributed_gate is not None:
                await self._distributed_gate.release(lease_token)
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
        if self._distributed_gate is not None:
            await self._distributed_gate.close()


class RedisModelConcurrencyGate:
    """Atomic cross-replica concurrency gate with expiring leases."""

    _ACQUIRE_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local expires = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local token = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
if redis.call('ZCARD', key) >= limit then return 0 end
redis.call('ZADD', key, expires, token)
redis.call('PEXPIRE', key, math.max(expires - now, 1000))
return 1
"""

    def __init__(self, *, redis_url: str, gate_name: str, limit: int, lease_seconds: int) -> None:
        from redis.asyncio import Redis

        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._key = f"hera:model-gate:{gate_name}"
        self._limit = limit
        self._lease_ms = lease_seconds * 1000

    async def acquire(self, *, timeout_seconds: float) -> str | None:
        deadline = time.monotonic() + timeout_seconds
        token = uuid.uuid4().hex
        while True:
            now_ms = int(time.time() * 1000)
            acquired = await self._client.eval(
                self._ACQUIRE_SCRIPT,
                1,
                self._key,
                now_ms,
                now_ms + self._lease_ms,
                self._limit,
                token,
            )
            if int(acquired) == 1:
                return token
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(0.05, remaining))

    async def release(self, token: str) -> None:
        await self._client.zrem(self._key, token)

    async def close(self) -> None:
        await self._client.aclose()


def build_llm_client(
    settings: Settings,
    *,
    model_override: str | None = None,
    provider_label_override: str | None = None,
) -> LLMClient:
    """Build the fixed FPT/OpenAI-compatible client with safe local degradation."""

    if settings.LLM_PROVIDER == "noop":
        return NoopLLMClient()
    client = _build_provider_client(
        settings.LLM_PROVIDER,
        settings,
        model_override=model_override,
        provider_label_override=provider_label_override,
    )
    if client is None:
        return NoopLLMClient()
    fallback_client: LLMClient = FallbackLLMClient([client])
    gate = None
    if settings.LLM_DISTRIBUTED_GATE_ENABLED:
        gate = RedisModelConcurrencyGate(
            redis_url=settings.REDIS_URL,
            gate_name=model_override or settings.FPT_LLM_MODEL,
            limit=settings.LLM_GLOBAL_MAX_CONCURRENT_REQUESTS,
            lease_seconds=settings.LLM_DISTRIBUTED_LEASE_SECONDS,
        )
    return GuardedLLMClient(
        fallback_client,
        max_concurrent_requests=settings.LLM_MAX_CONCURRENT_REQUESTS,
        queue_timeout_seconds=settings.LLM_QUEUE_TIMEOUT_SECONDS,
        cache_enabled=settings.LLM_RESPONSE_CACHE_ENABLED,
        cache_ttl_seconds=settings.LLM_RESPONSE_CACHE_TTL_SECONDS,
        cache_max_entries=settings.LLM_RESPONSE_CACHE_MAX_ENTRIES,
        settings=settings,
        distributed_gate=gate,
    )


def _build_provider_client(
    provider: str,
    settings: Settings,
    *,
    model_override: str | None = None,
    provider_label_override: str | None = None,
) -> LLMClient | None:
    if provider == "openai":
        use_fpt = bool(settings.API_KEY and settings.FPT_LLM_MODEL)
        api_key = settings.API_KEY if use_fpt else settings.OPENAI_API_KEY
        if not api_key:
            return None
        model = model_override or (
            settings.FPT_LLM_MODEL
            if use_fpt
            else (settings.OPENAI_MODEL or settings.LLM_MODEL)
        )
        provider_label = provider_label_override or (
            "fpt_llm" if use_fpt else "openai"
        )
        return OpenAILLMClient(
            api_key=api_key,
            model=model,
            base_url=(
                settings.FPT_API_BASE_URL if use_fpt else settings.OPENAI_BASE_URL
            ),
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            provider_label=provider_label,
            settings=settings,
            retry_max_attempts=settings.AI_PROVIDER_RETRY_MAX_ATTEMPTS,
            retry_base_delay_seconds=settings.AI_PROVIDER_RETRY_BASE_DELAY_SECONDS,
            retry_max_delay_seconds=settings.AI_PROVIDER_RETRY_MAX_DELAY_SECONDS,
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
    if stripped.startswith(SAFE_LLM_FALLBACK_PREFIX):
        return False
    return bool(stripped)


def _langfuse_usage_details(usage) -> dict[str, int]:
    details: dict[str, int] = {}
    if usage.input_tokens > 0:
        details["input"] = usage.input_tokens
    if usage.output_tokens > 0:
        details["output"] = usage.output_tokens
    total_tokens = usage.input_tokens + usage.output_tokens
    if total_tokens > 0:
        details["total"] = total_tokens
    return details
