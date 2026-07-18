"""Verify Langfuse authentication and ingestion without calling any model."""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dotenv import load_dotenv

_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = (
    _SCRIPT_PATH.parents[3]
    if len(_SCRIPT_PATH.parents) > 3
    else Path.cwd()
)
PROBE_NAME = "hera.langfuse_connectivity_probe"
MAX_POLL_TIMEOUT_SECONDS = 120.0
MAX_POLL_INTERVAL_SECONDS = 5.0


class LangfuseProbeError(RuntimeError):
    """Raised when Langfuse configuration or connectivity is not usable."""


@dataclass(frozen=True)
class LangfuseProbeConfig:
    """Only the Langfuse settings needed by this metadata-only probe."""

    enabled: bool
    public_key: str
    secret_key: str
    host: str

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> LangfuseProbeConfig:
        source = os.environ if environ is None else environ
        enabled_value = source.get("LANGFUSE_ENABLED", "").strip().lower()
        if enabled_value not in {"1", "true", "yes", "on"}:
            raise LangfuseProbeError(
                "LANGFUSE_ENABLED must be true before running the probe"
            )

        public_key = source.get("LANGFUSE_PUBLIC_KEY", "").strip()
        secret_key = source.get("LANGFUSE_SECRET_KEY", "").strip()
        if not public_key:
            raise LangfuseProbeError("LANGFUSE_PUBLIC_KEY is not configured")
        if not secret_key:
            raise LangfuseProbeError("LANGFUSE_SECRET_KEY is not configured")
        if public_key == secret_key:
            raise LangfuseProbeError(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must differ"
            )

        configured_host = source.get("LANGFUSE_HOST", "").strip()
        sdk_base_url = source.get("LANGFUSE_BASE_URL", "").strip()
        if configured_host and sdk_base_url:
            if _normalize_host(configured_host) != _normalize_host(sdk_base_url):
                raise LangfuseProbeError(
                    "LANGFUSE_HOST and LANGFUSE_BASE_URL must match when both are set"
                )
        host = configured_host or sdk_base_url
        if not host:
            raise LangfuseProbeError(
                "LANGFUSE_HOST (or LANGFUSE_BASE_URL) is not configured"
            )

        return cls(
            enabled=True,
            public_key=public_key,
            secret_key=secret_key,
            host=_normalize_host(host),
        )


def verify_langfuse(
    config: LangfuseProbeConfig,
    *,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 1.0,
    client_factory: Callable[..., Any] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    probe_id: str | None = None,
) -> dict[str, object]:
    """Authenticate, export one metadata-only span, and confirm it is readable."""

    _validate_polling(timeout_seconds, poll_interval_seconds)
    if not config.enabled:
        raise LangfuseProbeError("LANGFUSE_ENABLED must be true before running the probe")
    if not config.public_key or not config.secret_key:
        raise LangfuseProbeError("Langfuse credentials are not configured")
    host = _normalize_host(config.host)

    if client_factory is None:
        from langfuse import Langfuse

        client_factory = Langfuse

    request_timeout = max(1, min(10, int(timeout_seconds)))
    try:
        client = client_factory(
            public_key=config.public_key,
            secret_key=config.secret_key,
            host=host,
            timeout=request_timeout,
            tracing_enabled=True,
            sample_rate=1.0,
            environment="langfuse-check",
        )
    except Exception as exc:
        raise LangfuseProbeError("Could not initialize the Langfuse client") from exc

    try:
        try:
            authenticated = client.auth_check()
        except Exception as exc:
            raise LangfuseProbeError(
                "Langfuse authentication failed; verify the project keys and host"
            ) from exc
        if authenticated is not True:
            raise LangfuseProbeError(
                "Langfuse authentication failed; verify the project keys and host"
            )

        unique_probe_id = probe_id or secrets.token_hex(16)
        try:
            trace_id = client.create_trace_id(seed=unique_probe_id)
            with client.start_as_current_observation(
                name=PROBE_NAME,
                as_type="span",
                trace_context={"trace_id": trace_id},
                metadata={
                    "probe_id": unique_probe_id,
                    "probe_kind": "connectivity",
                    "model_api_calls": 0,
                    "contains_patient_content": False,
                },
            ):
                pass
            client.flush()
        except Exception as exc:
            raise LangfuseProbeError(
                "Langfuse accepted authentication but trace export failed"
            ) from exc

        deadline = monotonic() + timeout_seconds
        attempts = 0
        while True:
            attempts += 1
            try:
                trace = client.api.trace.get(trace_id)
                returned_trace_id = getattr(trace, "id", trace_id)
                if str(returned_trace_id) == trace_id:
                    return {
                        "status": "ok",
                        "probe_id": unique_probe_id,
                        "trace_id": trace_id,
                        "auth_check": True,
                        "trace_visible": True,
                        "poll_attempts": attempts,
                        "model_api_calls": 0,
                        "patient_content_sent": False,
                    }
            except Exception:
                # A just-exported trace commonly returns 404 until ingestion catches up.
                pass

            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            sleep(min(poll_interval_seconds, remaining))

        raise LangfuseProbeError(
            "Authentication succeeded, but the metadata probe was not visible "
            f"within {timeout_seconds:g} seconds"
        )
    finally:
        try:
            client.shutdown()
        except Exception:
            pass


def _normalize_host(value: str) -> str:
    host = value.strip().rstrip("/")
    if not host or any(character.isspace() for character in host):
        raise LangfuseProbeError("Langfuse host must be a valid HTTP(S) URL")
    try:
        parsed = urlsplit(host)
        _ = parsed.port
    except ValueError as exc:
        raise LangfuseProbeError("Langfuse host must be a valid HTTP(S) URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise LangfuseProbeError("Langfuse host must be a valid HTTP(S) URL")
    return host


def _validate_polling(timeout_seconds: float, poll_interval_seconds: float) -> None:
    if not 0 < timeout_seconds <= MAX_POLL_TIMEOUT_SECONDS:
        raise LangfuseProbeError(
            f"Probe timeout must be between 0 and {MAX_POLL_TIMEOUT_SECONDS:g} seconds"
        )
    if not 0 < poll_interval_seconds <= MAX_POLL_INTERVAL_SECONDS:
        raise LangfuseProbeError(
            "Poll interval must be between 0 and "
            f"{MAX_POLL_INTERVAL_SECONDS:g} seconds"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="Maximum time to wait for the exported trace (default: 30, max: 120).",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=1.0,
        help="Delay between trace reads (default: 1, max: 5).",
    )
    args = parser.parse_args()

    # Keep the CLI quiet even when the SDK rejects credentials. Error output below is
    # deliberately sanitized and never contains a key, URL, request, or response body.
    logging.getLogger("langfuse").setLevel(logging.CRITICAL)
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    try:
        config = LangfuseProbeConfig.from_environment()
        result = verify_langfuse(
            config,
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    except LangfuseProbeError as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": exc.__class__.__name__,
                    "detail": str(exc),
                    "model_api_calls": 0,
                    "patient_content_sent": False,
                }
            ),
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": exc.__class__.__name__,
                    "detail": "Unexpected Langfuse probe failure",
                    "model_api_calls": 0,
                    "patient_content_sent": False,
                }
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
