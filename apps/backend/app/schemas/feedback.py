"""Typed contract for the public feedback endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class FeedbackRequest(BaseModel):
    """Feedback associated with the request ID returned by chat."""

    request_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    helpful: bool
    reason_code: Literal[
        "inaccurate",
        "outdated",
        "unclear",
        "incomplete",
        "unsafe",
        "other",
    ] | None = None
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("request_id", "reason_code", "comment", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None


class FeedbackResponse(BaseModel):
    """Receipt proving feedback was accepted without echoing its comment."""

    feedback_id: str
    request_id: str
    accepted: bool = True
    created_at: str
