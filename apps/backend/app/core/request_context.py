"""Request-scoped logging context."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
conversation_id_var: ContextVar[str | None] = ContextVar(
    "conversation_id",
    default=None,
)


def bind_context(**values: Any) -> dict[str, Token]:
    """Bind request context values and return reset tokens."""

    tokens: dict[str, Token] = {}
    if "request_id" in values:
        tokens["request_id"] = request_id_var.set(_string_or_none(values["request_id"]))
    if "conversation_id" in values:
        tokens["conversation_id"] = conversation_id_var.set(
            _string_or_none(values["conversation_id"])
        )
    return tokens


def reset_context(tokens: dict[str, Token]) -> None:
    """Reset context variables using tokens returned by bind_context."""

    if "conversation_id" in tokens:
        conversation_id_var.reset(tokens["conversation_id"])
    if "request_id" in tokens:
        request_id_var.reset(tokens["request_id"])


def get_context() -> dict[str, str | None]:
    """Return current logging context fields."""

    return {
        "request_id": request_id_var.get(),
        "conversation_id": conversation_id_var.get(),
    }


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

