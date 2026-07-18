"""Feedback application service."""

from __future__ import annotations

from app.core.config import Settings
from app.persistence import ChatPersistenceRepository
from app.schemas.feedback import FeedbackRequest, FeedbackResponse


class FeedbackService:
    """Store a redacted feedback comment and return a content-free receipt."""

    def __init__(self, settings: Settings) -> None:
        self.repository = ChatPersistenceRepository(
            retention_days=settings.CONSENTED_MESSAGE_TTL_DAYS,
        )

    def submit(self, payload: FeedbackRequest) -> FeedbackResponse:
        stored = self.repository.record_feedback(
            request_id=payload.request_id,
            helpful=payload.helpful,
            reason_code=payload.reason_code,
            comment=payload.comment,
        )
        return FeedbackResponse(
            feedback_id=stored.feedback_id,
            request_id=stored.request_id,
            created_at=stored.created_at,
        )
