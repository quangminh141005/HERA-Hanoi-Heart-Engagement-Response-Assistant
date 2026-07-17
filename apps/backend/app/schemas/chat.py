"""Chat API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A grounded source citation for an assistant answer."""

    source_id: str
    title: str
    url: str | None = None
    excerpt: str | None = None


class ChatRequest(BaseModel):
    """Incoming chat request."""

    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    locale: str = "vi"
    user_context: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Assistant response returned to the frontend."""

    conversation_id: str
    response: str
    intent: str
    citations: list[Citation] = Field(default_factory=list)
    requires_handoff: bool = False
    emergency: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

