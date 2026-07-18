"""PostgreSQL persistence for consented chat turns and redacted feedback.

Raw user or assistant text is redacted before a database transaction starts.
The shared PostgreSQL database is the only runtime store, so retention and
audit behavior remain consistent across multiple backend replicas.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.privacy import redact_pii
from app.core.database import SessionLocal
from app.core.errors import HeraApiError

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class StoredTurn:
    """Non-sensitive receipt for one persistence decision."""

    stored: bool
    conversation_id: str
    user_message_id: str | None = None
    assistant_message_id: str | None = None


@dataclass(frozen=True)
class StoredFeedback:
    """Non-sensitive feedback receipt."""

    feedback_id: str
    request_id: str
    created_at: str


class ChatPersistenceRepository:
    """Persist redacted content and metadata through the pooled PG engine."""

    def __init__(
        self,
        *,
        retention_days: int,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self.retention_days = retention_days
        self.session_factory = session_factory or SessionLocal

    def record_chat_turn(
        self,
        *,
        request_id: str,
        conversation_id: str,
        consent_to_store: bool,
        user_content: str,
        assistant_content: str,
        response_type: str,
        data_classification: str,
        grounded: bool,
        intent: str,
        citations: list[dict[str, Any]],
        structured_record_ids: list[str],
    ) -> StoredTurn:
        """Store only consented/redacted messages; otherwise audit metadata only."""

        now = datetime.now(UTC)
        user_redaction = redact_pii(user_content) if consent_to_store else None
        assistant_redaction = (
            redact_pii(assistant_content) if consent_to_store else None
        )
        try:
            with self.session_factory() as db, db.begin():
                self._purge_expired(db, now=now)
                if not consent_to_store:
                    self._insert_audit(
                        db,
                        request_id=request_id,
                        event_type="chat_completed_without_content_storage",
                        object_type="chat_request",
                        object_id=None,
                        metadata={
                            "consent_to_store": False,
                            "intent": intent,
                            "response_type": response_type,
                            "grounded": grounded,
                            "citation_count": len(citations),
                            "structured_record_count": len(structured_record_ids),
                        },
                        created_at=now,
                    )
                    return StoredTurn(False, conversation_id)

                # Redaction completed before the transaction; raw content is
                # never used as a SQL bind parameter.
                assert user_redaction is not None
                assert assistant_redaction is not None
                expires_at = now + timedelta(days=self.retention_days)
                conversation_hash = hashlib.sha256(
                    f"hera-conversation:{conversation_id}".encode()
                ).hexdigest()
                db.execute(
                    text(
                        """
                        INSERT INTO conversations(
                            conversation_id, conversation_hash, consent_to_store,
                            created_at, expires_at
                        ) VALUES (
                            :conversation_id, :conversation_hash, TRUE,
                            :created_at, :expires_at
                        )
                        ON CONFLICT(conversation_id) DO UPDATE SET
                            conversation_hash = EXCLUDED.conversation_hash,
                            consent_to_store = TRUE,
                            expires_at = GREATEST(
                                conversations.expires_at,
                                EXCLUDED.expires_at
                            )
                        """
                    ),
                    {
                        "conversation_id": conversation_id,
                        "conversation_hash": conversation_hash,
                        "created_at": now,
                        "expires_at": expires_at,
                    },
                )

                user_message_id = uuid4().hex
                assistant_message_id = uuid4().hex
                db.execute(
                    text(
                        """
                        INSERT INTO chat_messages(
                            message_id, conversation_id, role, content_redacted,
                            response_type, data_classification, grounded,
                            request_id, created_at
                        ) VALUES (
                            :message_id, :conversation_id, 'user',
                            :content_redacted, NULL, 'user_input_redacted', NULL,
                            :request_id, :created_at
                        )
                        """
                    ),
                    {
                        "message_id": user_message_id,
                        "conversation_id": conversation_id,
                        "content_redacted": user_redaction.text,
                        "request_id": request_id,
                        "created_at": now,
                    },
                )
                db.execute(
                    text(
                        """
                        INSERT INTO chat_messages(
                            message_id, conversation_id, role, content_redacted,
                            response_type, data_classification, grounded,
                            request_id, created_at
                        ) VALUES (
                            :message_id, :conversation_id, 'assistant',
                            :content_redacted, :response_type,
                            :data_classification, :grounded,
                            :request_id, :created_at
                        )
                        """
                    ),
                    {
                        "message_id": assistant_message_id,
                        "conversation_id": conversation_id,
                        "content_redacted": assistant_redaction.text,
                        "response_type": response_type,
                        "data_classification": data_classification,
                        "grounded": grounded,
                        "request_id": request_id,
                        "created_at": now,
                    },
                )
                self._insert_citations(
                    db,
                    message_id=assistant_message_id,
                    citations=citations,
                )
                for record_id in dict.fromkeys(structured_record_ids):
                    db.execute(
                        text(
                            """
                            INSERT INTO structured_record_refs(
                                message_id, record_type, record_id,
                                data_classification
                            ) VALUES (
                                :message_id, :record_type, :record_id,
                                :data_classification
                            )
                            ON CONFLICT DO NOTHING
                            """
                        ),
                        {
                            "message_id": assistant_message_id,
                            "record_type": _record_type(record_id),
                            "record_id": record_id,
                            "data_classification": data_classification,
                        },
                    )

                self._insert_audit(
                    db,
                    request_id=request_id,
                    event_type="consented_chat_turn_stored",
                    object_type="conversation",
                    object_id=conversation_id,
                    metadata={
                        "consent_to_store": True,
                        "intent": intent,
                        "response_type": response_type,
                        "grounded": grounded,
                        "citation_count": len(citations),
                        "structured_record_count": len(structured_record_ids),
                        "redacted_input_categories": list(user_redaction.categories),
                        "redacted_output_categories": list(
                            assistant_redaction.categories
                        ),
                        "retention_days": self.retention_days,
                    },
                    created_at=now,
                )
                return StoredTurn(
                    True,
                    conversation_id,
                    user_message_id,
                    assistant_message_id,
                )
        except SQLAlchemyError as exc:
            raise _persistence_unavailable() from exc

    def record_feedback(
        self,
        *,
        request_id: str,
        helpful: bool,
        reason_code: str | None,
        comment: str | None,
    ) -> StoredFeedback:
        """Store redacted feedback and a content-free audit event."""

        now = datetime.now(UTC)
        feedback_id = uuid4().hex
        comment_redacted = None
        redacted_categories: tuple[str, ...] = ()
        if comment:
            redaction = redact_pii(comment.strip())
            comment_redacted = redaction.text or None
            redacted_categories = redaction.categories

        try:
            with self.session_factory() as db, db.begin():
                self._purge_expired(db, now=now)
                db.execute(
                    text(
                        """
                        INSERT INTO feedback(
                            feedback_id, request_id, helpful, reason_code,
                            comment_redacted, created_at
                        ) VALUES (
                            :feedback_id, :request_id, :helpful, :reason_code,
                            :comment_redacted, :created_at
                        )
                        """
                    ),
                    {
                        "feedback_id": feedback_id,
                        "request_id": request_id,
                        "helpful": helpful,
                        "reason_code": reason_code,
                        "comment_redacted": comment_redacted,
                        "created_at": now,
                    },
                )
                self._insert_audit(
                    db,
                    request_id=request_id,
                    event_type="feedback_recorded",
                    object_type="feedback",
                    object_id=feedback_id,
                    metadata={
                        "helpful": helpful,
                        "reason_code": reason_code,
                        "has_comment": comment_redacted is not None,
                        "redacted_comment_categories": list(redacted_categories),
                    },
                    created_at=now,
                )
        except SQLAlchemyError as exc:
            raise _persistence_unavailable() from exc
        return StoredFeedback(feedback_id, request_id, now.isoformat())

    @staticmethod
    def _insert_citations(
        db: Session,
        *,
        message_id: str,
        citations: list[dict[str, Any]],
    ) -> None:
        seen: set[str] = set()
        citation_order = 0
        for citation in citations:
            source_id = str(citation.get("source_id") or "").strip()
            if not source_id or source_id in seen:
                continue
            source_exists = db.execute(
                text(
                    """
                    SELECT 1 FROM official_sources
                    WHERE source_id = :source_id
                    """
                ),
                {"source_id": source_id},
            ).scalar_one_or_none()
            if source_exists is None:
                continue
            seen.add(source_id)
            excerpt = citation.get("excerpt")
            excerpt_redacted = (
                redact_pii(str(excerpt)).text[:1000] if excerpt is not None else None
            )
            db.execute(
                text(
                    """
                    INSERT INTO message_citations(
                        message_id, citation_order, source_id, fact_id, excerpt_vi
                    ) VALUES (
                        :message_id, :citation_order, :source_id, NULL, :excerpt
                    )
                    """
                ),
                {
                    "message_id": message_id,
                    "citation_order": citation_order,
                    "source_id": source_id,
                    "excerpt": excerpt_redacted,
                },
            )
            citation_order += 1

    def _purge_expired(self, db: Session, *, now: datetime) -> None:
        cutoff = now - timedelta(days=self.retention_days)
        # Child rows are removed by ON DELETE CASCADE from chat_messages.
        db.execute(
            text("DELETE FROM chat_messages WHERE created_at <= :cutoff"),
            {"cutoff": cutoff},
        )
        # handoff_events deliberately uses a nullable non-cascading reference.
        db.execute(
            text(
                """
                UPDATE handoff_events
                SET conversation_id = NULL
                WHERE conversation_id IN (
                    SELECT c.conversation_id
                    FROM conversations c
                    WHERE c.expires_at <= :now
                       OR NOT EXISTS (
                           SELECT 1 FROM chat_messages cm
                           WHERE cm.conversation_id = c.conversation_id
                       )
                )
                """
            ),
            {"now": now},
        )
        db.execute(
            text(
                """
                DELETE FROM conversations c
                WHERE c.expires_at <= :now
                   OR NOT EXISTS (
                       SELECT 1 FROM chat_messages cm
                       WHERE cm.conversation_id = c.conversation_id
                   )
                """
            ),
            {"now": now},
        )

    @staticmethod
    def _insert_audit(
        db: Session,
        *,
        request_id: str,
        event_type: str,
        object_type: str,
        object_id: str | None,
        metadata: dict[str, Any],
        created_at: datetime,
    ) -> None:
        db.execute(
            text(
                """
                INSERT INTO audit_events(
                    request_id, actor_type, event_type, object_type, object_id,
                    metadata_json, created_at
                ) VALUES (
                    :request_id, 'anonymous_user', :event_type, :object_type,
                    :object_id, CAST(:metadata_json AS JSONB), :created_at
                )
                """
            ),
            {
                "request_id": request_id,
                "event_type": event_type,
                "object_type": object_type,
                "object_id": object_id,
                "metadata_json": json.dumps(
                    metadata,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "created_at": created_at,
            },
        )


def _record_type(record_id: str) -> str:
    if record_id.startswith("SCHED-"):
        return "schedule_entry"
    if record_id.startswith("BHYT-") and "::" in record_id:
        return "bhyt_contribution_tier"
    if record_id.startswith("BHYT-"):
        return "bhyt_household_policy"
    if record_id.startswith("CHUNK-"):
        return "knowledge_chunk"
    if record_id.startswith("PRICE-") and record_id.endswith(("-CS1", "-CS2")):
        return "service_price_snapshot"
    if record_id.startswith("PRICE-"):
        return "service_catalog_record"
    return "structured_record"


def _persistence_unavailable() -> HeraApiError:
    return HeraApiError(
        code="PERSISTENCE_UNAVAILABLE",
        message_vi="HERA tạm thời chưa thể lưu dữ liệu. Vui lòng thử lại sau.",
        status_code=503,
        retryable=True,
    )
