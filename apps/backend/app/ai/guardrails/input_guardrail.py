"""Input guardrails for HERA chat requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class InputViolation(str, Enum):
    """Input violation categories."""

    PROMPT_INJECTION = "prompt_injection"
    MALICIOUS_PATTERN = "malicious_pattern"
    UNSAFE_MEDICAL_REQUEST = "unsafe_medical_request"


@dataclass(frozen=True)
class InputValidationResult:
    """Input validation result."""

    allowed: bool
    sanitized_text: str
    violation: InputViolation | None = None
    message: str | None = None


class InputGuardrail:
    """Validate user input before intent routing and generation."""

    INJECTION_PATTERNS = (
        r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions",
        r"(show|reveal|print|dump|repeat)\s+(your\s+)?(system\s+)?(prompt|instructions|rules)",
        r"system\s+override",
        r"jailbreak",
        r"bypass\s+(all\s+)?safety",
        r"(bo|bỏ)\s+qua\s+(huong dan|hướng dẫn|luat|luật)",
    )
    SQL_PATTERNS = (
        r"'\s*or\s*'",
        r"';\s*--",
        r"union\s+select.+--",
        r";\s*(drop\s+table|delete\s+from|update\s+\w+\s+set)\b",
    )
    UNSAFE_MEDICAL_PATTERNS = (
        r"\b(tu dieu tri|tự điều trị|ke don|kê đơn|uống thuốc gì)\b",
        r"\b(prescribe|dosage|diagnose me|what medicine should i take)\b",
    )

    def __init__(self) -> None:
        self.injection_regexes = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.INJECTION_PATTERNS
        ]
        self.sql_regexes = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.SQL_PATTERNS
        ]
        self.unsafe_medical_regexes = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.UNSAFE_MEDICAL_PATTERNS
        ]

    def validate(self, text: str) -> InputValidationResult:
        """Validate and sanitize text."""

        sanitized = self.sanitize(text)
        if not sanitized:
            return InputValidationResult(
                allowed=False,
                sanitized_text="",
                violation=InputViolation.MALICIOUS_PATTERN,
                message="Please enter a question.",
            )

        if match := _first_match(self.injection_regexes, sanitized):
            return InputValidationResult(
                allowed=False,
                sanitized_text=sanitized,
                violation=InputViolation.PROMPT_INJECTION,
                message=f"Prompt injection pattern detected: {match}",
            )
        if match := _first_match(self.sql_regexes, sanitized):
            return InputValidationResult(
                allowed=False,
                sanitized_text=sanitized,
                violation=InputViolation.MALICIOUS_PATTERN,
                message=f"Malicious input pattern detected: {match}",
            )
        if match := _first_match(self.unsafe_medical_regexes, sanitized):
            return InputValidationResult(
                allowed=False,
                sanitized_text=sanitized,
                violation=InputViolation.UNSAFE_MEDICAL_REQUEST,
                message=f"Unsafe medical request detected: {match}",
            )
        return InputValidationResult(allowed=True, sanitized_text=sanitized)

    def sanitize(self, text: str) -> str:
        """Remove null bytes, excessive whitespace, and overly long input."""

        clean = text.replace("\x00", "")
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:4000]


def _first_match(regexes: list[re.Pattern], text: str) -> str | None:
    for regex in regexes:
        match = regex.search(text)
        if match:
            return match.group(0)
    return None

