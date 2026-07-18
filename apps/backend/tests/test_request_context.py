"""Opaque request identifiers must be safe for logs and trace metadata."""

from __future__ import annotations

from app.core.request_context import normalize_request_id


def test_safe_request_id_is_preserved() -> None:
    assert normalize_request_id("request-123:abc") == "request-123:abc"


def test_pii_or_control_characters_are_not_used_as_request_id() -> None:
    normalized = normalize_request_id("patient@example.com\nforged")

    assert normalized != "patient@example.com\nforged"
    assert len(normalized) == 32
    assert normalized.isalnum()
