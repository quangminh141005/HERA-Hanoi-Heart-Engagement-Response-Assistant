"""Output guardrails for HERA assistant responses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class OutputViolation(str, Enum):
    """Output violation categories."""

    PROMPT_LEAK = "prompt_leak"
    UNSAFE_MEDICAL_ADVICE = "unsafe_medical_advice"
    UNGROUNDED_CLAIM = "ungrounded_claim"


@dataclass(frozen=True)
class OutputValidationResult:
    """Output validation result."""

    allowed: bool
    violation: OutputViolation | None = None
    message: str | None = None


class OutputGuardrail:
    """Validate generated responses before returning to users."""

    PROMPT_LEAK_PATTERNS = (
        r"\b(system prompt|developer message|hidden instructions?)\s*:",
        r"\bhere is my (system prompt|hidden instruction)",
    )
    MEDICAL_ADVICE_PATTERNS = (
        r"\b(take|use|increase|decrease)\s+\d+\s*(mg|ml)\b",
        r"\b(chẩn đoán|chan doan)\s+(chắc chắn|la|là)\b",
        r"\b(kê|ke)\s+đơn\b",
    )

    def __init__(self) -> None:
        self.prompt_leak_regexes = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.PROMPT_LEAK_PATTERNS
        ]
        self.medical_advice_regexes = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.MEDICAL_ADVICE_PATTERNS
        ]

    def validate(
        self,
        text: str,
        *,
        has_citations: bool,
        requires_grounding: bool,
    ) -> OutputValidationResult:
        """Validate assistant output."""

        if match := _first_match(self.prompt_leak_regexes, text):
            return OutputValidationResult(
                allowed=False,
                violation=OutputViolation.PROMPT_LEAK,
                message=f"Prompt leak pattern detected: {match}",
            )
        if match := _first_match(self.medical_advice_regexes, text):
            return OutputValidationResult(
                allowed=False,
                violation=OutputViolation.UNSAFE_MEDICAL_ADVICE,
                message=f"Unsafe medical advice pattern detected: {match}",
            )
        if requires_grounding and not has_citations:
            return OutputValidationResult(
                allowed=False,
                violation=OutputViolation.UNGROUNDED_CLAIM,
                message="Grounded hospital answer requires official citations.",
            )
        return OutputValidationResult(allowed=True)


def _first_match(regexes: list[re.Pattern], text: str) -> str | None:
    for regex in regexes:
        match = regex.search(text)
        if match:
            return match.group(0)
    return None

