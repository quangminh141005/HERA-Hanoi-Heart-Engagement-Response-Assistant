"""Conversation memory interfaces."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from time import monotonic
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversationEntities:
    """Whitelisted, server-approved entities kept for one short conversation."""

    intent: str
    facility_code: str | None = None
    service_name: str | None = None
    service_date: str | None = None
    doctor_name: str | None = None
    session_id: str | None = None
    bhyt_tier: int | None = None
    record_ids: tuple[str, ...] = ()


class EntityMemoryStore(Protocol):
    """Safe entity-only memory shared by the conversation orchestrator."""

    async def load(self, conversation_id: str) -> ConversationEntities | None: ...

    async def put(
        self,
        conversation_id: str,
        entities: ConversationEntities,
    ) -> None: ...

    async def clear(self, conversation_id: str) -> None: ...


@dataclass(frozen=True)
class _ExpiringEntities:
    value: ConversationEntities
    expires_at: float


class EphemeralEntityMemoryStore:
    """Bounded in-process entity memory; raw chat content is never retained."""

    def __init__(self, *, ttl_minutes: int = 30, max_conversations: int = 5_000):
        self._ttl_seconds = max(60, ttl_minutes * 60)
        self._max_conversations = max(1, max_conversations)
        self._entries: OrderedDict[str, _ExpiringEntities] = OrderedDict()
        self._lock = asyncio.Lock()

    async def load(self, conversation_id: str) -> ConversationEntities | None:
        """Return current safe entities and remove an expired entry eagerly."""

        now = monotonic()
        async with self._lock:
            entry = self._entries.get(conversation_id)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(conversation_id, None)
                return None
            self._entries.move_to_end(conversation_id)
            return entry.value

    async def put(
        self,
        conversation_id: str,
        entities: ConversationEntities,
    ) -> None:
        """Store only normalized identifiers and labels sourced from approved data."""

        safe = _normalize_entities(entities)
        now = monotonic()
        async with self._lock:
            self._purge_expired(now)
            self._entries[conversation_id] = _ExpiringEntities(
                value=safe,
                expires_at=now + self._ttl_seconds,
            )
            self._entries.move_to_end(conversation_id)
            while len(self._entries) > self._max_conversations:
                self._entries.popitem(last=False)

    async def clear(self, conversation_id: str) -> None:
        """Forget one conversation immediately."""

        async with self._lock:
            self._entries.pop(conversation_id, None)

    def _purge_expired(self, now: float) -> None:
        expired = [
            conversation_id
            for conversation_id, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for conversation_id in expired:
            self._entries.pop(conversation_id, None)


class RedisEntityMemoryStore:
    """Cross-replica entity memory with hashed keys and server-side TTL."""

    def __init__(
        self,
        *,
        redis_url: str,
        ttl_minutes: int = 30,
        client=None,
    ) -> None:
        self._ttl_seconds = max(60, ttl_minutes * 60)
        if client is not None:
            self._client = client
            return
        from redis.asyncio import Redis

        self._client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            retry_on_timeout=False,
            health_check_interval=30,
        )

    async def load(self, conversation_id: str) -> ConversationEntities | None:
        try:
            raw = await self._client.get(_redis_memory_key(conversation_id))
            if not raw:
                return None
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("entity payload is not an object")
            return _normalize_entities(
                ConversationEntities(
                    intent=str(payload.get("intent", "unknown")),
                    facility_code=_optional_string(payload.get("facility_code")),
                    service_name=_optional_string(payload.get("service_name")),
                    service_date=_optional_string(payload.get("service_date")),
                    doctor_name=_optional_string(payload.get("doctor_name")),
                    session_id=_optional_string(payload.get("session_id")),
                    bhyt_tier=_optional_int(payload.get("bhyt_tier")),
                    record_ids=tuple(
                        item
                        for item in payload.get("record_ids", [])
                        if isinstance(item, str)
                    ),
                )
            )
        except Exception as exc:
            logger.warning(
                "redis entity memory read failed; continuing without context",
                extra={
                    "event": "entity_memory_read_failed",
                    "error_type": exc.__class__.__name__,
                },
            )
            return None

    async def put(
        self,
        conversation_id: str,
        entities: ConversationEntities,
    ) -> None:
        safe = _normalize_entities(entities)
        payload = json.dumps(
            {
                "intent": safe.intent,
                "facility_code": safe.facility_code,
                "service_name": safe.service_name,
                "service_date": safe.service_date,
                "doctor_name": safe.doctor_name,
                "session_id": safe.session_id,
                "bhyt_tier": safe.bhyt_tier,
                "record_ids": list(safe.record_ids),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            await self._client.set(
                _redis_memory_key(conversation_id),
                payload,
                ex=self._ttl_seconds,
            )
        except Exception as exc:
            logger.warning(
                "redis entity memory write failed; turn remains stateless",
                extra={
                    "event": "entity_memory_write_failed",
                    "error_type": exc.__class__.__name__,
                },
            )

    async def clear(self, conversation_id: str) -> None:
        try:
            await self._client.delete(_redis_memory_key(conversation_id))
        except Exception as exc:
            logger.warning(
                "redis entity memory clear failed",
                extra={
                    "event": "entity_memory_clear_failed",
                    "error_type": exc.__class__.__name__,
                },
            )

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()


_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SAFE_INTENT = re.compile(r"^[a-z0-9_]{1,64}$")


def _normalize_entities(entities: ConversationEntities) -> ConversationEntities:
    intent = entities.intent if _SAFE_INTENT.fullmatch(entities.intent) else "unknown"
    facility = entities.facility_code
    if facility not in {"CS1", "CS2"}:
        facility = None
    service_date = entities.service_date
    if service_date:
        try:
            service_date = date.fromisoformat(service_date).isoformat()
        except ValueError:
            service_date = None
    tier = entities.bhyt_tier if entities.bhyt_tier in range(1, 6) else None
    record_ids = tuple(
        item
        for item in entities.record_ids[:10]
        if _SAFE_ID.fullmatch(item)
    )
    session_id = entities.session_id
    if session_id and not _SAFE_ID.fullmatch(session_id):
        session_id = None
    return ConversationEntities(
        intent=intent,
        facility_code=facility,
        service_name=_clean_approved_label(entities.service_name),
        service_date=service_date,
        doctor_name=_clean_approved_label(entities.doctor_name),
        session_id=session_id,
        bhyt_tier=tier,
        record_ids=record_ids,
    )


def _clean_approved_label(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = " ".join(value.split())[:160]
    return collapsed or None


def _redis_memory_key(conversation_id: str) -> str:
    digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
    return f"hera:conversation-entities:v1:{digest}"


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None

