from __future__ import annotations

import asyncio
import json

import app.ai.memory.store as memory_module
from app.ai.agent.orchestrator import build_default_orchestrator
from app.ai.memory import (
    ConversationEntities,
    EphemeralEntityMemoryStore,
    RedisEntityMemoryStore,
)
from app.core.config import Settings
from app.services.structured import StructuredChatResult


class FakeStructuredDataService:
    def chat_service_price(self, message: str) -> StructuredChatResult:
        lowered = message.lower()
        facility = "CS2" if "cs2" in lowered or "cơ sở 2" in lowered else "CS1"
        return StructuredChatResult(
            intent="service_price_current",
            response="Kết quả giá đã kiểm thử.",
            citations=[],
            metadata={
                "structured_action": {
                    "facility_code": facility,
                    "records": [
                        {
                            "facility_code": facility,
                            "display_name": "Giá Khám bệnh",
                        }
                    ],
                }
            },
            grounded=False,
            structured_record_ids=("PRICE-TEST",),
        )

    def chat_schedule(self, message: str) -> StructuredChatResult:
        lowered = message.lower()
        facility = "CS2" if "cs2" in lowered or "cơ sở 2" in lowered else "CS1"
        return StructuredChatResult(
            intent="schedule",
            response="Kết quả lịch đã kiểm thử.",
            citations=[],
            metadata={
                "structured_action": {
                    "facility_code": facility,
                    "records": [
                        {
                            "facility_code": facility,
                            "service_date": "2026-07-17",
                            "provider_text": "Bác sĩ kiểm thử",
                        }
                    ],
                }
            },
            grounded=False,
            structured_record_ids=("SCHEDULE-TEST",),
        )

    def support_actions(self) -> tuple[dict, ...]:
        return ()


def test_ephemeral_memory_expires_and_normalizes_entities(monkeypatch) -> None:
    now = 100.0
    monkeypatch.setattr(memory_module, "monotonic", lambda: now)
    store = EphemeralEntityMemoryStore(ttl_minutes=1)

    async def scenario() -> None:
        await store.put(
            "conversation-memory-001",
            ConversationEntities(
                intent="schedule",
                facility_code="UNAPPROVED",
                service_date="not-a-date",
                session_id="unsafe token value",
                record_ids=("SCHEDULE-001", "contains whitespace"),
            ),
        )
        value = await store.load("conversation-memory-001")
        assert value is not None
        assert value.facility_code is None
        assert value.service_date is None
        assert value.session_id is None
        assert value.record_ids == ("SCHEDULE-001",)

        nonlocal now
        now += 61
        assert await store.load("conversation-memory-001") is None

    asyncio.run(scenario())


def test_multiturn_uses_approved_entities_and_resets_on_intent_switch() -> None:
    settings = Settings(
        LLM_PROVIDER="noop",
        EMBEDDING_PROVIDER="noop",
        RATE_LIMIT_ENABLED=False,
        _env_file=None,
    )
    orchestrator = build_default_orchestrator(settings)
    orchestrator.structured_data_service = FakeStructuredDataService()
    conversation_id = "conversation-context-001"

    async def scenario() -> None:
        first = await orchestrator.handle(
            message="Giá khám bệnh cơ sở 1 là bao nhiêu?",
            conversation_id=conversation_id,
            locale="vi",
            user_context={},
        )
        assert first.intent == "service_price_current"

        follow_up = await orchestrator.handle(
            message="Còn cơ sở 2 thì sao?",
            conversation_id=conversation_id,
            locale="vi",
            user_context={},
        )
        assert follow_up.intent == "service_price_current"
        assert follow_up.metadata["ephemeral_context_applied"] is True
        price_records = follow_up.metadata["structured_action"]["records"]
        assert price_records
        assert price_records[0]["facility_code"] == "CS2"

        short_follow_up = await orchestrator.handle(
            message="Vậy bao nhiêu?",
            conversation_id=conversation_id,
            locale="vi",
            user_context={},
        )
        assert short_follow_up.intent == "service_price_current"
        assert short_follow_up.metadata["ephemeral_context_applied"] is True

        switched = await orchestrator.handle(
            message="Lịch bác sĩ cơ sở 1 ngày 2026-07-17",
            conversation_id=conversation_id,
            locale="vi",
            user_context={},
        )
        assert switched.intent == "schedule"

        schedule_follow_up = await orchestrator.handle(
            message="Còn cơ sở 2 thì sao?",
            conversation_id=conversation_id,
            locale="vi",
            user_context={},
        )
        assert schedule_follow_up.intent == "schedule"
        assert schedule_follow_up.metadata["ephemeral_context_applied"] is True

    asyncio.run(scenario())


def test_rag_overall_deadline_returns_safe_handoff() -> None:
    settings = Settings(
        LLM_PROVIDER="noop",
        EMBEDDING_PROVIDER="noop",
        CHAT_OVERALL_TIMEOUT_SECONDS=0.01,
        RATE_LIMIT_ENABLED=False,
        _env_file=None,
    )
    orchestrator = build_default_orchestrator(settings)
    orchestrator.structured_data_service = FakeStructuredDataService()

    class SlowRag:
        async def answer(self, *args, **kwargs):
            del args, kwargs
            await asyncio.sleep(0.1)
            raise AssertionError("deadline should cancel slow RAG")

    orchestrator.rag_pipeline = SlowRag()

    result = asyncio.run(
        orchestrator.handle(
            message="Quy trình khám gồm những gì?",
            conversation_id="conversation-timeout-001",
            locale="vi",
            user_context={},
        )
    )

    assert result.response_type == "refusal_and_handoff"
    assert result.requires_handoff is True
    assert result.metadata == {
        "upstream_timeout": "rag_pipeline",
        "decision_source": "deterministic_fallback",
    }


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.expirations[key] = ex

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.expirations.pop(key, None)


def test_redis_entity_memory_is_cross_replica_hashed_and_entity_only() -> None:
    redis = _FakeRedis()
    writer = RedisEntityMemoryStore(
        redis_url="redis://unused",
        ttl_minutes=7,
        client=redis,
    )
    reader = RedisEntityMemoryStore(
        redis_url="redis://unused",
        ttl_minutes=7,
        client=redis,
    )
    conversation_id = "patient-phone-0900000000-conversation"

    async def scenario() -> None:
        await writer.put(
            conversation_id,
            ConversationEntities(
                intent="schedule",
                facility_code="CS1",
                service_date="2026-07-19",
                doctor_name="Bac si Nguyen Van A",
                session_id="SESSION-001",
                record_ids=("SCHEDULE-001",),
            ),
        )

        assert len(redis.values) == 1
        key, raw_value = next(iter(redis.values.items()))
        assert conversation_id not in key
        assert "0900000000" not in key
        assert key.startswith("hera:conversation-entities:v1:")
        assert redis.expirations[key] == 7 * 60

        payload = json.loads(raw_value)
        assert set(payload) == {
            "intent",
            "facility_code",
            "service_name",
            "service_date",
            "doctor_name",
            "session_id",
            "bhyt_tier",
            "record_ids",
        }
        assert raw_value.find("0900000000") == -1

        loaded = await reader.load(conversation_id)
        assert loaded is not None
        assert loaded.session_id == "SESSION-001"
        assert loaded.record_ids == ("SCHEDULE-001",)

        await reader.clear(conversation_id)
        assert await writer.load(conversation_id) is None

    asyncio.run(scenario())
