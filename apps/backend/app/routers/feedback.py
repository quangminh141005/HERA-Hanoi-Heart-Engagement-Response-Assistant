"""Public feedback route."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, status

from app.core.config import get_settings
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.services.feedback import FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])


@lru_cache(maxsize=1)
def get_feedback_service() -> FeedbackService:
    return FeedbackService(get_settings())


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    payload: FeedbackRequest,
    service: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    """Accept helpfulness feedback; free text is redacted before persistence."""

    return service.submit(payload)
