"""Deterministic PII redaction before persistence or model calls."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RedactionResult:
    text: str
    categories: tuple[str, ...]


_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "email",
        re.compile(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"),
        "[EMAIL_ĐÃ_ẨN]",
    ),
    (
        "phone",
        re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.-]?\d){9,10}(?!\d)"),
        "[SỐ_ĐIỆN_THOẠI_ĐÃ_ẨN]",
    ),
    (
        "cccd",
        re.compile(r"(?<!\d)\d{12}(?!\d)"),
        "[CCCD_ĐÃ_ẨN]",
    ),
    (
        "bhyt_card",
        re.compile(r"(?<![A-Z0-9])[A-Z]{2}\d{13}(?![A-Z0-9])", re.IGNORECASE),
        "[THẺ_BHYT_ĐÃ_ẨN]",
    ),
)


def redact_pii(text: str) -> RedactionResult:
    redacted = text
    found: list[str] = []
    for category, pattern, replacement in _PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            found.append(category)
    return RedactionResult(text=redacted, categories=tuple(found))
