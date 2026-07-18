"""Chat routes for the HERA customer-care assistant."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, Request

from app.core.config import get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@lru_cache(maxsize=1)
def get_chat_service() -> ChatService:
    """Reuse model HTTP clients, immutable data services, and short entity memory."""

    return ChatService(settings=get_settings())


async def close_chat_service() -> None:
    if get_chat_service.cache_info().currsize:
        await get_chat_service().close()
        get_chat_service.cache_clear()


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """Handle one user chat turn."""

    return await service.respond(
        payload,
        request_id=getattr(request.state, "request_id", "unknown"),
    )
