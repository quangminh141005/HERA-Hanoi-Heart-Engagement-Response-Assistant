from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from scripts.verify_langfuse import (
    PROBE_NAME,
    LangfuseProbeConfig,
    LangfuseProbeError,
    verify_langfuse,
)


@dataclass
class _Trace:
    id: str


class _TraceAPI:
    def __init__(self, *, failures_before_visible: int | None) -> None:
        self.failures_before_visible = failures_before_visible
        self.calls = 0

    def get(self, trace_id: str) -> _Trace:
        self.calls += 1
        if (
            self.failures_before_visible is None
            or self.calls <= self.failures_before_visible
        ):
            raise RuntimeError("not visible")
        return _Trace(id=trace_id)


class _ObservationContext:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, *args: object) -> None:
        del args


class _FakeClient:
    def __init__(
        self,
        *,
        authenticated: bool = True,
        failures_before_visible: int | None = 1,
    ) -> None:
        self.authenticated = authenticated
        self.api = type("API", (), {})()
        self.api.trace = _TraceAPI(
            failures_before_visible=failures_before_visible
        )
        self.start_kwargs: dict[str, Any] | None = None
        self.flushed = False
        self.shutdown_called = False

    def auth_check(self) -> bool:
        return self.authenticated

    def create_trace_id(self, *, seed: str) -> str:
        assert seed
        return "a" * 32

    def start_as_current_observation(self, **kwargs: Any) -> _ObservationContext:
        self.start_kwargs = kwargs
        return _ObservationContext()

    def flush(self) -> None:
        self.flushed = True

    def shutdown(self) -> None:
        self.shutdown_called = True


def _config() -> LangfuseProbeConfig:
    return LangfuseProbeConfig(
        enabled=True,
        public_key="public-test-key",
        secret_key="secret-test-key",
        host="https://cloud.langfuse.com",
    )


def test_config_accepts_base_url_alias_without_exposing_values() -> None:
    config = LangfuseProbeConfig.from_environment(
        {
            "LANGFUSE_ENABLED": "true",
            "LANGFUSE_PUBLIC_KEY": "public-test-key",
            "LANGFUSE_SECRET_KEY": "secret-test-key",
            "LANGFUSE_BASE_URL": "https://cloud.langfuse.com/",
        }
    )

    assert config.host == "https://cloud.langfuse.com"


def test_probe_exports_metadata_only_and_waits_until_visible() -> None:
    client = _FakeClient(failures_before_visible=1)
    factory_kwargs: dict[str, Any] = {}
    clock = [0.0]

    def factory(**kwargs: Any) -> _FakeClient:
        factory_kwargs.update(kwargs)
        return client

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    result = verify_langfuse(
        _config(),
        timeout_seconds=3,
        poll_interval_seconds=1,
        client_factory=factory,
        monotonic=lambda: clock[0],
        sleep=sleep,
        probe_id="safe-probe-id",
    )

    assert factory_kwargs["sample_rate"] == 1.0
    assert factory_kwargs["tracing_enabled"] is True
    assert client.start_kwargs == {
        "name": PROBE_NAME,
        "as_type": "span",
        "trace_context": {"trace_id": "a" * 32},
        "metadata": {
            "probe_id": "safe-probe-id",
            "probe_kind": "connectivity",
            "model_api_calls": 0,
            "contains_patient_content": False,
        },
    }
    assert client.flushed is True
    assert client.shutdown_called is True
    assert result["trace_visible"] is True
    assert result["model_api_calls"] == 0
    assert result["patient_content_sent"] is False


def test_probe_stops_at_bounded_timeout() -> None:
    client = _FakeClient(failures_before_visible=None)
    clock = [0.0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    with pytest.raises(LangfuseProbeError, match="not visible"):
        verify_langfuse(
            _config(),
            timeout_seconds=2,
            poll_interval_seconds=1,
            client_factory=lambda **kwargs: client,
            monotonic=lambda: clock[0],
            sleep=sleep,
            probe_id="safe-probe-id",
        )

    assert clock[0] == 2
    assert client.api.trace.calls == 3
    assert client.shutdown_called is True


def test_auth_failure_does_not_export_a_probe() -> None:
    client = _FakeClient(authenticated=False)

    with pytest.raises(LangfuseProbeError, match="authentication failed"):
        verify_langfuse(
            _config(),
            client_factory=lambda **kwargs: client,
        )

    assert client.start_kwargs is None
    assert client.flushed is False
    assert client.shutdown_called is True
