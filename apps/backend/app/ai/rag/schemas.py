"""RAG data contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeSource(BaseModel):
    """Metadata for an official hospital knowledge source."""

    source_id: str
    title: str
    url: str | None = None
    document_type: str | None = None
    scope: str | None = None
    effective_date: str | None = None


class RetrievedChunk(BaseModel):
    """One retrieved text chunk from official sources."""

    chunk_id: str
    text: str
    score: float = 0.0
    source: KnowledgeSource


class RetrievalRequest(BaseModel):
    """Retrieval request contract."""

    query: str
    top_k: int = Field(default=5, ge=1)
    locale: str = "vi"
    allowed_intents: list[str] = Field(default_factory=list)


class RetrievalResponse(BaseModel):
    """Retrieval response contract."""

    query: str
    chunks: list[RetrievedChunk] = Field(default_factory=list)


class GroundedAnswer(BaseModel):
    """Generated answer and citations."""

    answer: str
    citations: list[KnowledgeSource] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    generation_mode: str = "deterministic"
    validation_issues: list[str] = Field(default_factory=list)

