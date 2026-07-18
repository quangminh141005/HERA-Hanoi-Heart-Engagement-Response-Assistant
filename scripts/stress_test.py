"""Local HTTP stress test for PostgreSQL reads and atomic booking capacity.

The script never calls a model endpoint. Run it only against the dedicated local
stress Compose overlay, never against a public hospital deployment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx

PROFILES = {
    "ci": {"read_requests": 200, "booking_requests": 80, "concurrency": 20},
    "standard": {
        "read_requests": 5_000,
        "booking_requests": 1_000,
        "concurrency": 200,
    },
    "extreme": {
        "read_requests": 50_000,
        "booking_requests": 10_000,
        "concurrency": 1_000,
    },
}


@dataclass(frozen=True)
class RequestResult:
    status: int
    duration_ms: float
    code: str | None = None
    replica: str | None = None
    payload: dict[str, Any] | None = None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil((percentile / 100) * len(ordered)) - 1)
    return round(ordered[index], 2)


def _summary(results: list[RequestResult], elapsed: float) -> dict[str, Any]:
    durations = [item.duration_ms for item in results]
    statuses = Counter(str(item.status) for item in results)
    codes = Counter(item.code for item in results if item.code)
    replicas = sorted({item.replica for item in results if item.replica})
    success = sum(1 for item in results if 200 <= item.status < 300)
    return {
        "requests": len(results),
        "success": success,
        "failures": len(results) - success,
        "error_rate": round((len(results) - success) / max(1, len(results)), 6),
        "throughput_rps": round(len(results) / max(elapsed, 0.001), 2),
        "latency_ms": {
            "min": round(min(durations, default=0.0), 2),
            "mean": round(statistics.fmean(durations), 2) if durations else 0.0,
            "p50": _percentile(durations, 50),
            "p95": _percentile(durations, 95),
            "p99": _percentile(durations, 99),
            "max": round(max(durations, default=0.0), 2),
        },
        "statuses": dict(sorted(statuses.items())),
        "error_codes": dict(sorted(codes.items())),
        "replicas": replicas,
        "replica_count": len(replicas),
    }


async def _request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> RequestResult:
    started = perf_counter()
    try:
        response = await client.request(
            method,
            path,
            json=json_body,
            headers={
                "X-Request-ID": f"stress-{uuid4().hex}",
                **(headers or {}),
            },
        )
        try:
            value = response.json()
            payload = value if isinstance(value, dict) else None
        except ValueError:
            payload = None
        error = payload.get("error") if isinstance(payload, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        return RequestResult(
            status=response.status_code,
            duration_ms=(perf_counter() - started) * 1_000,
            code=code if isinstance(code, str) else None,
            replica=response.headers.get("X-HERA-Replica"),
            payload=payload,
        )
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        return RequestResult(
            status=0,
            duration_ms=(perf_counter() - started) * 1_000,
            code=exc.__class__.__name__,
        )


async def _bounded_requests(
    total: int,
    concurrency: int,
    operation,
) -> list[RequestResult]:
    queue: asyncio.Queue[int] = asyncio.Queue()
    for index in range(total):
        queue.put_nowait(index)
    results: list[RequestResult] = []

    async def worker() -> None:
        while True:
            try:
                index = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                results.append(await operation(index))
            finally:
                queue.task_done()

    workers = [
        asyncio.create_task(worker())
        for _ in range(min(total, max(1, concurrency)))
    ]
    await asyncio.gather(*workers)
    return results


def _read_paths() -> tuple[str, ...]:
    price = urlencode({"query": "khám", "facility_code": "CS1"})
    schedule = urlencode({"week_start": "2026-07-13", "facility_code": "CS2"})
    return (
        f"/api/v1/service-prices?{price}",
        "/api/v1/bhyt/household-contributions",
        f"/api/v1/schedules?{schedule}",
        "/api/v1/booking-sessions",
        "/healthz",
    )


async def _run_reads(
    client: httpx.AsyncClient,
    *,
    requests: int,
    concurrency: int,
) -> dict[str, Any]:
    paths = _read_paths()
    started = perf_counter()
    results = await _bounded_requests(
        requests,
        concurrency,
        lambda index: _request(client, "GET", paths[index % len(paths)]),
    )
    elapsed = perf_counter() - started
    report = _summary(results, elapsed)
    report["passed"] = report["failures"] == 0
    return report


def _session_records(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def _synthetic_patient(index: int) -> dict[str, str]:
    """Return a valid non-real patient identity for local hold stress tests."""

    serial = f"{index:06d}"
    return {
        "full_name": f"Stress Test {serial}",
        "phone_number": f"090{index % 10_000_000:07d}",
        "cccd_number": f"001{index % 1_000_000_000:09d}",
        "bhyt_card_number": f"ST{index % 1_000_000_000:09d}",
    }


async def _run_booking(
    client: httpx.AsyncClient,
    *,
    requests: int,
    concurrency: int,
) -> dict[str, Any]:
    sessions_result = await _request(client, "GET", "/api/v1/booking-sessions")
    sessions = [
        item
        for item in _session_records(sessions_result.payload)
        if int(item.get("remaining_count", 0)) > 0
    ]
    if sessions_result.status != 200 or not sessions:
        return {
            "passed": False,
            "reason": "no_open_booking_session",
            "preflight_status": sessions_result.status,
        }
    session = sessions[0]
    session_id = str(session["booking_session_id"])
    capacity = int(session["capacity_limit"])
    occupied_before = int(session["occupied_count"])
    remaining_before = int(session["remaining_count"])

    async def hold(index: int) -> RequestResult:
        unique = f"{index}-{uuid4().hex}"
        return await _request(
            client,
            "POST",
            "/api/v1/booking-holds",
            json_body={
                "booking_session_id": session_id,
                "idempotency_key": f"stress-idempotency-{unique}",
                "patient": _synthetic_patient(index),
            },
            headers={"X-Anonymous-Session-ID": f"stress-owner-{unique}"},
        )

    started = perf_counter()
    results = await _bounded_requests(requests, concurrency, hold)
    elapsed = perf_counter() - started
    accepted = [
        item
        for item in results
        if item.status == 201 and isinstance(item.payload, dict)
    ]
    expected_accepted = min(requests, remaining_before)
    allowed_rejections = {"CAPACITY_REACHED"}
    unexpected = [
        item
        for item in results
        if item.status != 201 and item.code not in allowed_rejections
    ]

    refreshed = await _request(client, "GET", "/api/v1/booking-sessions")
    refreshed_session = next(
        (
            item
            for item in _session_records(refreshed.payload)
            if item.get("booking_session_id") == session_id
        ),
        None,
    )
    occupied_after = (
        int(refreshed_session["occupied_count"])
        if refreshed_session is not None
        else -1
    )
    invariant = (
        len(accepted) == expected_accepted
        and occupied_after == occupied_before + len(accepted)
        and occupied_after <= capacity
        and not unexpected
    )

    async def release(item: RequestResult) -> RequestResult:
        assert item.payload is not None
        return await _request(
            client,
            "DELETE",
            f"/api/v1/booking-holds/{item.payload['hold_id']}",
            headers={"Authorization": f"Bearer {item.payload['hold_token']}"},
        )

    release_results = await asyncio.gather(*(release(item) for item in accepted))
    cleanup_ok = all(item.status == 200 for item in release_results)
    after_cleanup = await _request(client, "GET", "/api/v1/booking-sessions")
    clean_session = next(
        (
            item
            for item in _session_records(after_cleanup.payload)
            if item.get("booking_session_id") == session_id
        ),
        None,
    )
    occupied_clean = (
        int(clean_session["occupied_count"]) if clean_session is not None else -1
    )
    cleanup_ok = cleanup_ok and occupied_clean == occupied_before

    report = _summary(results, elapsed)
    report.update(
        {
            "passed": bool(invariant and cleanup_ok),
            "session_id": session_id,
            "capacity_limit": capacity,
            "occupied_before": occupied_before,
            "occupied_peak": occupied_after,
            "occupied_after_cleanup": occupied_clean,
            "accepted_holds": len(accepted),
            "expected_accepted_holds": expected_accepted,
            "capacity_rejections": sum(
                1 for item in results if item.code == "CAPACITY_REACHED"
            ),
            "unexpected_results": len(unexpected),
            "capacity_invariant": invariant,
            "cleanup_ok": cleanup_ok,
        }
    )
    return report


async def run(args: argparse.Namespace) -> dict[str, Any]:
    profile = PROFILES[args.profile]
    request_count = args.requests or int(profile["read_requests"])
    booking_count = args.booking_requests or int(profile["booking_requests"])
    concurrency = args.concurrency or int(profile["concurrency"])
    timeout = httpx.Timeout(40.0, connect=5.0, pool=40.0)
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=min(concurrency, 500),
    )
    report: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "profile": args.profile,
        "scenario": args.scenario,
        "base_url": args.base_url,
        "model_api_calls": 0,
        "configuration": {
            "read_requests": request_count,
            "booking_requests": booking_count,
            "concurrency": concurrency,
        },
    }
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=timeout,
        limits=limits,
        trust_env=False,
    ) as client:
        ready = await _request(client, "GET", "/readyz")
        if ready.status != 200:
            report.update(
                {
                    "passed": False,
                    "preflight": {"readyz_status": ready.status, "code": ready.code},
                }
            )
            return report
        if args.scenario in {"reads", "mixed"}:
            report["reads"] = await _run_reads(
                client,
                requests=request_count,
                concurrency=concurrency,
            )
        if args.scenario in {"booking", "mixed"}:
            report["booking"] = await _run_booking(
                client,
                requests=booking_count,
                concurrency=concurrency,
            )
    checks = [
        value.get("passed") is True
        for key, value in report.items()
        if key in {"reads", "booking"} and isinstance(value, dict)
    ]
    replicas_seen = sorted(
        {
            replica
            for key in ("reads", "booking")
            for replica in (
                report.get(key, {}).get("replicas", [])
                if isinstance(report.get(key), dict)
                else []
            )
        }
    )
    report["replicas_seen"] = replicas_seen
    report["minimum_replicas_required"] = args.min_replicas
    report["horizontal_distribution_passed"] = (
        len(replicas_seen) >= args.min_replicas
    )
    report["passed"] = bool(
        checks and all(checks) and report["horizontal_distribution_passed"]
    )
    report["finished_at"] = datetime.now(UTC).isoformat()
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="standard")
    parser.add_argument(
        "--scenario",
        choices=("reads", "booking", "mixed"),
        default="mixed",
    )
    parser.add_argument("--requests", type=int, default=None)
    parser.add_argument("--booking-requests", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--min-replicas", type=int, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/stress/latest.json"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    for name in ("requests", "booking_requests", "concurrency", "min_replicas"):
        value = getattr(args, name)
        if value is not None and value < 1:
            raise SystemExit(f"--{name.replace('_', '-')} must be positive")
    report = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("passed") else 2


if __name__ == "__main__":
    sys.exit(main())
