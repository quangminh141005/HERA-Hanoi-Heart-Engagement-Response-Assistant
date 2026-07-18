"""Privacy guarantees for optional Langfuse tracing."""

from __future__ import annotations

from app.ai.observability import tracing
from app.core.config import Settings


class CapturedObservation:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class ObservationManager:
    def __init__(self, observation: CapturedObservation) -> None:
        self.observation = observation

    def __enter__(self):
        return self.observation

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback
        return False


class CapturedClient:
    def __init__(self) -> None:
        self.start_kwargs = None
        self.observation = CapturedObservation()

    def start_as_current_observation(self, **kwargs):
        self.start_kwargs = kwargs
        return ObservationManager(self.observation)


def test_disabled_tracing_is_noop() -> None:
    settings = Settings(LANGFUSE_ENABLED=False, _env_file=None)

    with tracing.start_observation("hera.chat", settings=settings) as observation:
        observation.update(metadata={"intent": "booking"})

    assert isinstance(observation, tracing.NoopObservation)


def test_langfuse_base_url_alias_overrides_default_host() -> None:
    settings = Settings(
        LANGFUSE_ENABLED=False,
        LANGFUSE_BASE_URL="https://us.cloud.langfuse.com/",
        _env_file=None,
    )

    assert settings.LANGFUSE_HOST == "https://us.cloud.langfuse.com"


def test_tracing_drops_input_and_output_when_content_capture_is_disabled(
    monkeypatch,
) -> None:
    client = CapturedClient()
    monkeypatch.setattr(tracing, "_client_for", lambda settings: client)
    settings = Settings(
        LANGFUSE_ENABLED=True,
        LANGFUSE_PUBLIC_KEY="public",
        LANGFUSE_SECRET_KEY="secret",
        LANGFUSE_CAPTURE_CONTENT=False,
        _env_file=None,
    )

    with tracing.start_observation(
        "hera.chat",
        settings=settings,
        input="raw patient message",
        user_id="patient@example.com",
        metadata={"request_id": "request-1", "nested": {"raw": "blocked"}},
    ) as observation:
        observation.update(
            input="raw patient message",
            output="raw assistant answer",
            metadata={"intent": "booking", "nested": {"raw": "blocked"}},
            user_id="patient@example.com",
        )

    assert "input" not in client.start_kwargs
    assert "user_id" not in client.start_kwargs
    assert client.start_kwargs["metadata"] == {"request_id": "request-1"}
    assert client.observation.updates == [{"metadata": {"intent": "booking"}}]
