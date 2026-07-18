from __future__ import annotations

from stress_test import PROFILES, RequestResult, _summary


def test_stress_profiles_are_monotonic_and_extreme_is_large() -> None:
    assert PROFILES["ci"]["read_requests"] < PROFILES["standard"]["read_requests"]
    assert (
        PROFILES["standard"]["read_requests"]
        < PROFILES["extreme"]["read_requests"]
    )
    assert PROFILES["extreme"]["read_requests"] >= 50_000
    assert PROFILES["extreme"]["concurrency"] >= 1_000


def test_stress_summary_reports_tail_latency_and_failures() -> None:
    results = [
        RequestResult(status=200, duration_ms=float(value), replica="replica-a")
        for value in range(1, 100)
    ]
    results.append(
        RequestResult(status=429, duration_ms=100.0, code="RATE_LIMITED")
    )

    report = _summary(results, elapsed=2.0)

    assert report["requests"] == 100
    assert report["success"] == 99
    assert report["failures"] == 1
    assert report["error_rate"] == 0.01
    assert report["throughput_rps"] == 50.0
    assert report["latency_ms"]["p50"] == 50.0
    assert report["latency_ms"]["p95"] == 95.0
    assert report["latency_ms"]["p99"] == 99.0
    assert report["error_codes"] == {"RATE_LIMITED": 1}
    assert report["replicas"] == ["replica-a"]
    assert report["replica_count"] == 1
