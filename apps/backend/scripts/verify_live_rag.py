#!/usr/bin/env python3
"""Prove that the deployed RAG path uses live LLM and embedding providers."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings, get_settings  # noqa: E402


class LiveRagProbeError(RuntimeError):
    """Raised when the deployed path cannot prove live model-backed RAG."""


_MOJIBAKE_SIGNATURES = (
    "áº",
    "á»",
    "Ä‘",
    "Æ°",
    "Æ¡",
    "â€",
    "â€¢",
    "\ufffd",
)


def verify_live_rag(
    settings: Settings,
    *,
    base_url: str,
    metrics_url: str,
    timeout_seconds: float = 45.0,
) -> dict[str, object]:
    """Run one unique grounded question and require live provider token deltas."""

    _validate_model_configuration(settings)
    before = _fetch_metrics(metrics_url, timeout_seconds=5.0)
    probe_id = uuid4().hex[:10]
    query = (
        "Tôi đã đặt hẹn khám, nên tới bệnh viện trước giờ hẹn bao lâu để "
        f"hoàn tất thủ tục ban đầu? Mã kiểm tra hệ thống {probe_id}."
    )
    started = time.perf_counter()
    raw, content_type = _post_json(
        f"{base_url.rstrip('/')}/api/v1/chat",
        {
            "message": query,
            "locale": "vi-VN",
            "consent_to_store": False,
            "client_context": {"channel": "live_rag_release_probe"},
        },
        timeout_seconds=timeout_seconds,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    try:
        decoded = raw.decode("utf-8", errors="strict")
        payload = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveRagProbeError("Chat response is not strict UTF-8 JSON") from exc

    _validate_response(payload, decoded=decoded, content_type=content_type)
    after = _fetch_metrics(metrics_url, timeout_seconds=5.0)
    deltas = _provider_deltas(before, after)
    missing_usage = [name for name, value in deltas.items() if value <= 0]
    if missing_usage:
        raise LiveRagProbeError(
            "Live provider usage was not observed for: " + ", ".join(missing_usage)
        )

    failure_delta = _failure_delta(before, after)
    if failure_delta > 0:
        raise LiveRagProbeError("FPT provider failure/timeout metrics increased")

    return {
        "status": "ok",
        "llm_model": settings.FPT_LLM_MODEL,
        "embedding_model": settings.FPT_EMBEDDING_MODEL,
        "embedding_dimensions": settings.EMBEDDING_DIMENSIONS,
        "decision_source": payload["metadata"]["decision_source"],
        "generation_mode": payload["metadata"]["generation_mode"],
        "grounded": payload["grounded"],
        "citation_count": len(payload["citations"]),
        "elapsed_ms": elapsed_ms,
        **deltas,
        "provider_failure_delta": failure_delta,
        "strict_utf8": True,
        "synthetic_input_only": True,
    }


def _validate_model_configuration(settings: Settings) -> None:
    if not settings.API_KEY:
        raise LiveRagProbeError("API_KEY is not configured")
    if settings.FPT_LLM_MODEL != "gpt-oss-120b":
        raise LiveRagProbeError("FPT_LLM_MODEL must be gpt-oss-120b")
    if settings.FPT_EMBEDDING_MODEL != "Vietnamese_Embedding":
        raise LiveRagProbeError(
            "FPT_EMBEDDING_MODEL must be Vietnamese_Embedding"
        )
    if settings.EMBEDDING_DIMENSIONS != 1024:
        raise LiveRagProbeError("EMBEDDING_DIMENSIONS must be 1024")


def _validate_response(
    payload: dict[str, Any],
    *,
    decoded: str,
    content_type: str,
) -> None:
    metadata = payload.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    checks = {
        "JSON response must declare UTF-8": "charset=utf-8" in content_type.lower(),
        "routing did not use the model": metadata.get("decision_source") == "model",
        "generation was not model-validated": (
            metadata.get("generation_mode") == "model_validated"
        ),
        "answer is not grounded": payload.get("grounded") is True,
        "answer has no official citation": bool(payload.get("citations")),
        "expected approved fact is absent": bool(
            re.search(r"15\s+phút", str(payload.get("answer_vi", "")))
        ),
        "response contains a mojibake signature": not any(
            signature in decoded for signature in _MOJIBAKE_SIGNATURES
        ),
    }
    failures = [message for message, passed in checks.items() if not passed]
    if failures:
        raise LiveRagProbeError("; ".join(failures))


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: float,
) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "X-Request-ID": f"live-rag-probe-{uuid4().hex[:12]}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
        return raw, response.headers.get("Content-Type", "")


def _fetch_metrics(url: str, *, timeout_seconds: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="strict")


def _provider_deltas(before: str, after: str) -> dict[str, float]:
    labels = (
        ("llm_input_tokens", "fpt_llm", "input"),
        ("llm_output_tokens", "fpt_llm", "output"),
        ("embedding_input_tokens", "fpt_embedding", "input"),
    )
    return {
        f"{name}_delta": _metric_value(
            after,
            "hera_ai_tokens_total",
            provider=provider,
            kind=kind,
        )
        - _metric_value(
            before,
            "hera_ai_tokens_total",
            provider=provider,
            kind=kind,
        )
        for name, provider, kind in labels
    }


def _failure_delta(before: str, after: str) -> float:
    total = 0.0
    for metric in (
        "hera_upstream_failures_total",
        "hera_upstream_timeouts_total",
    ):
        for provider in ("fpt_llm", "fpt_embedding"):
            total += _metric_value(after, metric, provider=provider) - _metric_value(
                before,
                metric,
                provider=provider,
            )
    return total


def _metric_value(
    text: str,
    metric: str,
    *,
    provider: str,
    kind: str | None = None,
) -> float:
    for line in text.splitlines():
        if not line.startswith(f"{metric}{{"):
            continue
        label_text, raw_value = line.rsplit("}", 1)
        labels = {}
        for pair in label_text.split("{", 1)[1].split(","):
            key, value = pair.split("=", 1)
            labels[key] = value.strip('"')
        if labels.get("provider") != provider:
            continue
        if kind is not None and labels.get("kind") != kind:
            continue
        return float(raw_value.strip().split()[0])
    return 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://frontend")
    parser.add_argument(
        "--metrics-url",
        default="http://127.0.0.1:8000/metrics",
    )
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()
    try:
        result = verify_live_rag(
            get_settings(),
            base_url=args.base_url,
            metrics_url=args.metrics_url,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        detail = (
            str(exc)
            if isinstance(exc, LiveRagProbeError)
            else "Live RAG probe failed; inspect backend logs and Langfuse."
        )
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": exc.__class__.__name__,
                    "detail": detail,
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
