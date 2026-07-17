"""Chat orchestration service."""

from __future__ import annotations

from app.ai.agent.orchestrator import build_default_orchestrator
from app.core.config import Settings
from app.schemas.chat import ChatRequest, ChatResponse, Citation


class ChatService:
    """Application service for assistant chat requests."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.orchestrator = build_default_orchestrator(settings)

    async def respond(self, request: ChatRequest) -> ChatResponse:
        """Process a chat request through the HERA assistant pipeline."""

        result = await self.orchestrator.handle(
            message=request.message,
            conversation_id=request.conversation_id,
            locale=request.locale,
            user_context=request.user_context,
        )
        return ChatResponse(
            conversation_id=result.conversation_id,
            response=result.response,
            intent=result.intent,
            citations=[Citation(**source) for source in result.citations],
            requires_handoff=result.requires_handoff,
            emergency=result.emergency,
            metadata=result.metadata,
        )

