"""Chat routes for the HERA customer-care assistant."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


async def get_chat_service() -> ChatService:
    """Build a chat service for the current request."""

    return ChatService(settings=get_settings())


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """Handle one user chat turn."""

    return await service.respond(request)
