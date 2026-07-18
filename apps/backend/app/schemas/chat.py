"""Chat API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A grounded source citation for an assistant answer."""

    source_id: str
    fact_id: str | None = None
    title: str
    url: str | None = None
    excerpt: str | None = None
    publisher: str | None = None
    effective_from: str | None = None


class ChatRequest(BaseModel):
    """Incoming chat request."""

    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(
        default=None,
        min_length=16,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    locale: str = "vi-VN"
    consent_to_store: bool = False
    client_context: dict[str, Any] = Field(default_factory=dict)
    # Backward-compatible alias used by the original Vite scaffold.
    user_context: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Assistant response returned to the frontend."""

    request_id: str
    conversation_id: str
    response: str
    answer_vi: str
    response_type: str
    intent: str
    grounded: bool
    data_classification: str
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structured_record_ids: list[str] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    requires_handoff: bool = False
    emergency: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

