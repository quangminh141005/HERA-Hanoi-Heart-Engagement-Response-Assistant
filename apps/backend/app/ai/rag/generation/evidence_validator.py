"""Deterministic checks that prevent new factual tokens in RAG output."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceValidation:
    allowed: bool
    issues: tuple[str, ...] = ()


_NUMBER = re.compile(r"(?<!\w)\d[\d.,:/-]*\d|(?<!\w)\d(?!\w)")
_URL = re.compile(r"https?://[^\s)\]}>]+", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:115|1900\d{4,8}|0\d{9,10})(?!\d)")
_STOP_WORDS = {
    "ban",
    "cac",
    "cho",
    "co",
    "cua",
    "da",
    "de",
    "duoc",
    "he",
    "la",
    "minh",
    "mot",
    "nhung",
    "theo",
    "thong",
    "tin",
    "toi",
    "tra",
    "va",
    "voi",
}


def validate_against_evidence(
    answer: str,
    *,
    query: str,
    evidence: list[str],
) -> EvidenceValidation:
    """Allow a paraphrase only when its factual surface is supported."""

    support_text = "\n".join([query, *evidence])
    support_folded = _fold(support_text)
    issues: list[str] = []

    for kind, pattern in (("number", _NUMBER), ("url", _URL), ("phone", _PHONE)):
        supported = {_fold(item) for item in pattern.findall(support_text)}
        introduced = {
            item
            for item in (_fold(value) for value in pattern.findall(answer))
            if item not in supported
        }
        if introduced:
            issues.append(f"unsupported_{kind}")

    answer_tokens = _content_tokens(answer)
    if answer_tokens:
        supported_count = sum(
            1 for token in answer_tokens if token in support_folded.split()
        )
        coverage = supported_count / len(answer_tokens)
        if coverage < 0.55:
            issues.append("low_lexical_support")

    return EvidenceValidation(allowed=not issues, issues=tuple(sorted(set(issues))))


def _content_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _fold(value))
        if len(token) > 1 and token not in _STOP_WORDS and not token.isdigit()
    }


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.lower())
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return without_marks.replace("đ", "d")
