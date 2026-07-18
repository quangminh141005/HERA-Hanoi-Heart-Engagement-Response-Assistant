"""Provider-reported token accounting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderTokenUsage:
    """Normalized OpenAI-compatible usage fields."""

    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0


def extract_openai_usage(response: Any) -> ProviderTokenUsage:
    """Normalize Chat Completions and Responses-style usage field aliases.

    OpenAI-compatible gateways commonly expose either prompt/completion or
    input/output names. Reasoning tokens are normally already included in the
    completion total; taking the maximum of the reported totals counts them
    without charging the same tokens twice.
    """

    usage = _field(response, "usage")
    if usage is None:
        return ProviderTokenUsage()

    input_tokens = _first_nonnegative_int(
        _field(usage, "prompt_tokens"),
        _field(usage, "input_tokens"),
    )
    reported_output_tokens = _first_nonnegative_int(
        _field(usage, "completion_tokens"),
        _field(usage, "output_tokens"),
    )

    completion_details = _field(usage, "completion_tokens_details")
    output_details = _field(usage, "output_tokens_details")
    reasoning_tokens = max(
        _nonnegative_int(_field(usage, "reasoning_tokens")),
        _nonnegative_int(_field(completion_details, "reasoning_tokens")),
        _nonnegative_int(_field(output_details, "reasoning_tokens")),
    )

    total_tokens = _nonnegative_int(_field(usage, "total_tokens"))
    derived_output_tokens = max(total_tokens - input_tokens, 0) if total_tokens else 0
    output_tokens = max(
        reported_output_tokens,
        reasoning_tokens,
        derived_output_tokens,
    )
    return ProviderTokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def extract_openai_embedding_usage(response: Any) -> ProviderTokenUsage:
    """Normalize input-only embedding usage, accepting total_tokens fallback."""

    usage = _field(response, "usage")
    if usage is None:
        return ProviderTokenUsage()
    input_tokens = _first_nonnegative_int(
        _field(usage, "prompt_tokens"),
        _field(usage, "input_tokens"),
        _field(usage, "total_tokens"),
    )
    return ProviderTokenUsage(input_tokens=input_tokens)


def _field(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _first_nonnegative_int(*values: Any) -> int:
    for value in values:
        if value is not None:
            return _nonnegative_int(value)
    return 0


def _nonnegative_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return max(int(value), 0)
    except (TypeError, ValueError, OverflowError):
        return 0
