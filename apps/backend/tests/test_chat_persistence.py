"""Fast persistence/service tests; real PostgreSQL coverage is integration-only."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.core.errors import HeraApiError
from app.main import app
from app.observability.prometheus import (
    AI_RESPONSES_TOTAL,
    EMERGENCY_HANDOFFS_TOTAL,
    GUARDRAIL_BLOCKS_TOTAL,
)
from app.persistence.chat_repository import (
    ChatPersistenceRepository,
    StoredFeedback,
)
from app.routers.feedback import get_feedback_service
from app.schemas.chat import ChatRequest
from app.services.chat import ChatService
from app.services.feedback import FeedbackService
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError


def test_postgres_persistence_has_no_sqlite_fallback() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "persistence"
        / "chat_repository.py"
    )
    implementation = source.read_text(encoding="utf-8")

    assert "SessionLocal" in implementation
    assert "sqlite3" not in implementation
    assert "STRUCTURED_DB_PATH" not in implementation
    assert "CAST(:metadata_json AS JSONB)" in implementation


def test_persistence_failure_is_stable_and_does_not_echo_database_detail() -> None:
    def unavailable_session():
        raise SQLAlchemyError("postgres secret detail")

    repository = ChatPersistenceRepository(
        retention_days=7,
        session_factory=unavailable_session,
    )

    with pytest.raises(HeraApiError) as error:
        repository.record_feedback(
            request_id="request-database-unavailable",
            helpful=False,
            reason_code="other",
            comment=None,
        )

    assert error.value.code == "PERSISTENCE_UNAVAILABLE"
    assert error.value.retryable is True
    assert "secret" not in str(error.value)


def test_chat_service_instruments_safety_metrics_without_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_type = "test_guardrail_response"
    violation_type = "test_prompt_injection"
    ai_counter = AI_RESPONSES_TOTAL.labels(
        response_type=response_type,
        grounded="false",
    )
    guardrail_counter = GUARDRAIL_BLOCKS_TOTAL.labels(
        violation_type=violation_type,
    )
    ai_before = ai_counter._value.get()
    emergency_before = EMERGENCY_HANDOFFS_TOTAL._value.get()
    guardrail_before = guardrail_counter._value.get()
    trace: dict[str, object] = {}

    class FakeObservation:
        def update(self, **kwargs):
            trace["update"] = kwargs

    @contextmanager
    def fake_start_observation(name, **kwargs):
        trace["name"] = name
        trace["start"] = kwargs
        yield FakeObservation()

    monkeypatch.setattr(
        "app.services.chat.start_observation",
        fake_start_observation,
    )

    class FakeOrchestrator:
        async def handle(self, **_kwargs):
            return SimpleNamespace(
                conversation_id="metric-conversation-001",
                response="Nội dung an toàn.",
                response_type=response_type,
                intent="unsupported",
                grounded=False,
                data_classification="insufficient_data",
                citations=[],
                warnings=[],
                structured_record_ids=[],
                actions=[],
                requires_handoff=True,
                emergency=True,
                metadata={"guardrail_violation": violation_type},
            )

    class FakePersistence:
        def record_chat_turn(self, **kwargs):
            assert kwargs["consent_to_store"] is False

    service = ChatService.__new__(ChatService)
    service.settings = Settings(
        RATE_LIMIT_ENABLED=False,
        LANGFUSE_ENABLED=False,
        _env_file=None,
    )
    service.orchestrator = FakeOrchestrator()
    service.persistence = FakePersistence()
    result = asyncio.run(
        service.respond(
            ChatRequest(
                message="Không lưu nội dung này",
                client_context={"channel": "hospital_web"},
            ),
            request_id="metric-request-001",
        )
    )

    assert result.request_id == "metric-request-001"
    assert ai_counter._value.get() == ai_before + 1
    assert EMERGENCY_HANDOFFS_TOTAL._value.get() == emergency_before + 1
    assert guardrail_counter._value.get() == guardrail_before + 1
    assert trace["name"] == "hera.chat_turn"
    assert "Không lưu nội dung này" not in repr(trace)
    assert "Nội dung an toàn" not in repr(trace)


def test_chat_service_records_trace_input_and_output_when_capture_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace: dict[str, object] = {}

    class FakeObservation:
        def update(self, **kwargs):
            trace["update"] = kwargs

    @contextmanager
    def fake_start_observation(name, **kwargs):
        trace["name"] = name
        trace["start"] = kwargs
        yield FakeObservation()

    monkeypatch.setattr(
        "app.services.chat.start_observation",
        fake_start_observation,
    )

    class FakeOrchestrator:
        async def handle(self, **_kwargs):
            return SimpleNamespace(
                conversation_id="trace-conversation-001",
                response="Chào bạn, HERA có thể hỗ trợ thông tin bệnh viện.",
                response_type="non_factual",
                intent="greeting",
                grounded=False,
                data_classification="general",
                citations=[],
                warnings=[],
                structured_record_ids=[],
                actions=[],
                requires_handoff=False,
                emergency=False,
                metadata={"decision_source": "deterministic"},
            )

    class FakePersistence:
        def record_chat_turn(self, **kwargs):
            assert kwargs["user_content"] == "Xin chào HERA"

    service = ChatService.__new__(ChatService)
    service.settings = Settings(
        RATE_LIMIT_ENABLED=False,
        LANGFUSE_ENABLED=False,
        LANGFUSE_CAPTURE_CONTENT=True,
        _env_file=None,
    )
    service.orchestrator = FakeOrchestrator()
    service.persistence = FakePersistence()

    result = asyncio.run(
        service.respond(
            ChatRequest(
                message="Xin chào HERA",
                client_context={"channel": "hospital_web"},
            ),
            request_id="trace-request-001",
        )
    )

    assert result.response == "Chào bạn, HERA có thể hỗ trợ thông tin bệnh viện."
    assert trace["name"] == "hera.chat_turn"
    assert trace["start"]["input"] == {
        "message": "Xin chào HERA",
        "conversation_id": None,
        "locale": "vi",
        "channel": "hospital_web",
        "consent_to_store": False,
    }
    assert trace["update"]["output"]["response"] == result.response
    assert trace["update"]["output"]["intent"] == "greeting"


class FakeFeedbackRepository:
    def __init__(self, *, failure: HeraApiError | None = None) -> None:
        self.failure = failure
        self.submitted = None

    def record_feedback(self, **kwargs):
        if self.failure:
            raise self.failure
        self.submitted = kwargs
        return StoredFeedback(
            feedback_id="feedback-unit-001",
            request_id=kwargs["request_id"],
            created_at="2026-07-18T00:00:00+00:00",
        )


def _feedback_service(repository: FakeFeedbackRepository) -> FeedbackService:
    service = FeedbackService.__new__(FeedbackService)
    service.repository = repository
    return service


def test_feedback_endpoint_does_not_echo_comment() -> None:
    repository = FakeFeedbackRepository()
    service = _feedback_service(repository)
    app.dependency_overrides[get_feedback_service] = lambda: service
    raw_phone = "0987654321"
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/feedback",
                json={
                    "request_id": "request-feedback-unit-001",
                    "helpful": False,
                    "reason_code": "unclear",
                    "comment": f"Gọi lại cho tôi theo số {raw_phone}",
                },
            )
    finally:
        app.dependency_overrides.pop(get_feedback_service, None)

    assert response.status_code == 201
    assert response.json()["feedback_id"] == "feedback-unit-001"
    assert "comment" not in response.json()
    assert raw_phone not in response.text
    assert repository.submitted["comment"].endswith(raw_phone)


def test_feedback_validation_has_stable_error_shape() -> None:
    app.dependency_overrides[get_feedback_service] = lambda: _feedback_service(
        FakeFeedbackRepository()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/feedback",
                json={"request_id": "bad request id", "helpful": True},
            )
    finally:
        app.dependency_overrides.pop(get_feedback_service, None)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_feedback_database_failure_has_stable_retryable_error() -> None:
    failure = HeraApiError(
        code="PERSISTENCE_UNAVAILABLE",
        message_vi="HERA tạm thời chưa thể lưu dữ liệu. Vui lòng thử lại sau.",
        status_code=503,
        retryable=True,
    )
    service = _feedback_service(FakeFeedbackRepository(failure=failure))
    app.dependency_overrides[get_feedback_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/feedback",
                json={
                    "request_id": "request-database-unavailable",
                    "helpful": False,
                    "reason_code": "other",
                },
            )
    finally:
        app.dependency_overrides.pop(get_feedback_service, None)

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "PERSISTENCE_UNAVAILABLE"
    assert error["retryable"] is True
    assert error["request_id"] == response.headers["X-Request-ID"]
