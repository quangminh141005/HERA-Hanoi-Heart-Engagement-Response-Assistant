"""HTTP integration tests for the FastAPI application boundary."""

from __future__ import annotations

import asyncio

import httpx
from app.main import app


async def _get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.get(path, headers={"X-Request-ID": "test-request"})


def test_health_check_returns_status_and_gateway_headers() -> None:
    response = asyncio.run(_get("/health"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["app"] == "HERA - Hanoi Heart Engagement Response Assistant"
    assert response.headers["X-Request-ID"] == "test-request"
    assert "X-Process-Time-Ms" in response.headers


def test_versioned_health_check() -> None:
    response = asyncio.run(_get("/api/v1/health"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def _exercise_health_then_metrics() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        await client.get("/health", headers={"X-Request-ID": "test-request"})
        return await client.get("/metrics")


def test_prometheus_metrics_endpoint_exposes_backend_metrics() -> None:
    response = asyncio.run(_exercise_health_then_metrics())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "hera_app_info" in response.text
    assert "hera_http_requests_total" in response.text

