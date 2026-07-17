"""Conversation memory interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MemoryMessage:
    """One conversation memory item."""

    role: str
    content: str


class ConversationMemoryStore(Protocol):
    """Memory store contract."""

    async def load(self, conversation_id: str) -> list[MemoryMessage]:
        """Load recent messages."""

    async def append(self, conversation_id: str, message: MemoryMessage) -> None:
        """Append one message."""


class NoopConversationMemoryStore:
    """No-op memory until persistence rules are approved."""

    async def load(self, conversation_id: str) -> list[MemoryMessage]:
        del conversation_id
        return []

    async def append(self, conversation_id: str, message: MemoryMessage) -> None:
        del conversation_id, message
        return None

