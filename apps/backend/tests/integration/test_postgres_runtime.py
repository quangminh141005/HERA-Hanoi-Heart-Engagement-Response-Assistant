"""Real PostgreSQL tests for replica-safe booking and private persistence.

Set ``HERA_TEST_DATABASE_URL`` to a migrated and seeded disposable HERA
database.  The fixture deletes only runtime rows; reference data is preserved.
No model or embedding endpoint is contacted.
"""

from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from app.booking import BookingRepository
from app.core.errors import HeraApiError
from app.persistence import ChatPersistenceRepository
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pg_session_factory() -> sessionmaker[Session]:
    database_url = os.getenv("HERA_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("HERA_TEST_DATABASE_URL is not configured")
    engine = create_engine(
        database_url,
        pool_size=24,
        max_overflow=8,
        pool_pre_ping=True,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        tables_ready = db.execute(
            text(
                """
                SELECT to_regclass('public.booking_sessions') IS NOT NULL
                   AND to_regclass('public.chat_messages') IS NOT NULL
                """
            )
        ).scalar_one()
        seeded_sessions = (
            db.execute(text("SELECT COUNT(*) FROM booking_sessions")).scalar_one()
            if tables_ready
            else 0
        )
    if not tables_ready or seeded_sessions < 2:
        engine.dispose()
        pytest.fail("PostgreSQL test database must be migrated and seeded")
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_runtime_rows(pg_session_factory: sessionmaker[Session]) -> None:
    _clean_runtime_rows(pg_session_factory)
    yield
    _clean_runtime_rows(pg_session_factory)


def _clean_runtime_rows(factory: sessionmaker[Session]) -> None:
    with factory() as db, db.begin():
        for table in (
            "message_citations",
            "structured_record_refs",
            "handoff_events",
            "chat_messages",
            "conversations",
            "feedback",
            "audit_events",
            "booking_holds",
        ):
            db.execute(text(f"DELETE FROM {table}"))


def _booking_repository(
    factory: sessionmaker[Session],
    *,
    owner_limit: int = 2,
) -> BookingRepository:
    return BookingRepository(
        hold_token_secret="postgres-test-secret-0123456789abcdef",
        hold_ttl_seconds=300,
        max_active_holds_per_owner=owner_limit,
        session_factory=factory,
    )


def _session_ids(factory: sessionmaker[Session], limit: int = 2) -> list[str]:
    with factory() as db:
        return list(
            db.execute(
                text(
                    """
                    SELECT booking_session_id
                    FROM booking_sessions
                    WHERE status = 'open' AND prototype_only = TRUE
                    ORDER BY booking_session_id
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).scalars()
        )


def _patient(index: int = 1) -> dict[str, str]:
    return {
        "full_name": f"Nguyen Van Test {index}",
        "phone_number": f"09123456{index:02d}",
        "cccd_number": f"001001000{index:03d}",
        "bhyt_card_number": f"DN401010000{index:02d}",
    }


def test_concurrent_capacity_is_atomic_across_connections(
    pg_session_factory: sessionmaker[Session],
) -> None:
    repository = _booking_repository(pg_session_factory)
    session_id = _session_ids(pg_session_factory, 1)[0]

    def attempt(index: int) -> str:
        try:
            repository.create_hold(
                booking_session_id=session_id,
                idempotency_key=f"postgres-concurrent-{index:02d}",
                owner_session_id=f"postgres-owner-{index:02d}",
                patient_identity=_patient(index),
            )
            return "held"
        except HeraApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=21) as executor:
        results = list(executor.map(attempt, range(21)))

    assert results.count("held") == 20
    assert results.count("CAPACITY_REACHED") == 1
    snapshot = repository.capacity_snapshot(session_id)
    assert snapshot == {"capacity_limit": 20, "occupied_count": 20}


def test_owner_quota_and_idempotency_are_atomic_across_sessions(
    pg_session_factory: sessionmaker[Session],
) -> None:
    repository = _booking_repository(pg_session_factory, owner_limit=1)
    first_session, second_session = _session_ids(pg_session_factory, 2)
    owner = "same-owner-across-two-sessions"

    def attempt(session_id: str) -> str:
        try:
            repository.create_hold(
                booking_session_id=session_id,
                idempotency_key=f"quota-{session_id}",
                owner_session_id=owner,
                patient_identity=_patient(1),
            )
            return "held"
        except HeraApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, (first_session, second_session)))
    assert results.count("held") == 1
    assert results.count("ACTIVE_HOLD_LIMIT_REACHED") == 1

    held_session = first_session if results[0] == "held" else second_session
    replay = repository.create_hold(
        booking_session_id=held_session,
        idempotency_key=f"quota-{held_session}",
        owner_session_id=owner,
        patient_identity=_patient(1),
    )
    assert replay["idempotent_replay"] is True


def test_hold_token_is_hashed_and_required_for_release(
    pg_session_factory: sessionmaker[Session],
) -> None:
    repository = _booking_repository(pg_session_factory)
    session_id = _session_ids(pg_session_factory, 1)[0]
    hold = repository.create_hold(
        booking_session_id=session_id,
        idempotency_key="postgres-release-operation",
        owner_session_id="postgres-release-owner",
        patient_identity=_patient(3),
    )

    with pg_session_factory() as db:
        stored = db.execute(
            text(
                """
                SELECT anonymous_token_hash, patient_phone_hash,
                       patient_phone_masked, patient_cccd_hash,
                       patient_bhyt_hash
                FROM booking_holds
                WHERE hold_id = :hold_id
                """
            ),
            {"hold_id": hold["hold_id"]},
        ).mappings().one()
    stored_hash = stored["anonymous_token_hash"]
    assert stored_hash == hashlib.sha256(hold["hold_token"].encode()).hexdigest()
    assert stored_hash != hold["hold_token"]
    stored_values = " ".join(str(value) for value in stored.values())
    assert "0912345603" not in stored_values
    assert "001001000003" not in stored_values
    assert "DN40101000003" not in stored_values
    assert stored["patient_phone_masked"].endswith("5603")

    with pytest.raises(HeraApiError) as error:
        repository.release_hold(hold_id=hold["hold_id"], token="wrong-token")
    assert error.value.code == "HOLD_TOKEN_INVALID"
    released = repository.release_hold(
        hold_id=hold["hold_id"],
        token=hold["hold_token"],
    )
    assert released["status"] == "released"
    assert isinstance(released["expires_at"], str)
    assert "anonymous_token_hash" not in released
    assert "owner_session_hash" not in released
    assert repository.capacity_snapshot(session_id)["occupied_count"] == 0


def test_chat_and_feedback_store_only_redacted_content(
    pg_session_factory: sessionmaker[Session],
) -> None:
    repository = ChatPersistenceRepository(
        retention_days=7,
        session_factory=pg_session_factory,
    )
    phone = "0912345678"
    email = "patient@example.com"

    no_consent = repository.record_chat_turn(
        request_id="postgres-request-no-consent",
        conversation_id="postgres-conversation-no-consent",
        consent_to_store=False,
        user_content=f"Số của tôi là {phone}",
        assistant_content="Nội dung không lưu",
        response_type="grounded_answer",
        data_classification="official_current",
        grounded=True,
        intent="schedule",
        citations=[],
        structured_record_ids=[],
    )
    assert no_consent.stored is False

    consented = repository.record_chat_turn(
        request_id="postgres-request-consented",
        conversation_id="postgres-conversation-consented",
        consent_to_store=True,
        user_content=f"Số của tôi là {phone}",
        assistant_content=f"Không gửi tới {email}",
        response_type="structured_action",
        data_classification="official_current",
        grounded=True,
        intent="service_price_current",
        citations=[
            {"source_id": "SRC-PRICE-2025", "excerpt": f"Liên hệ {phone}"}
        ],
        structured_record_ids=[
            "PRICE-2025-000001",
            "PRICE-2025-000001-CS1",
        ],
    )
    feedback = repository.record_feedback(
        request_id="postgres-request-consented",
        helpful=False,
        reason_code="unclear",
        comment=f"Gọi lại {phone}",
    )

    with pg_session_factory() as db:
        messages = list(
            db.execute(
                text(
                    """
                    SELECT content_redacted FROM chat_messages
                    WHERE conversation_id = :conversation_id
                    """
                ),
                {"conversation_id": consented.conversation_id},
            ).scalars()
        )
        citation = db.execute(
            text("SELECT excerpt_vi FROM message_citations")
        ).scalar_one()
        feedback_comment = db.execute(
            text(
                """
                SELECT comment_redacted FROM feedback
                WHERE feedback_id = :feedback_id
                """
            ),
            {"feedback_id": feedback.feedback_id},
        ).scalar_one()
        conversation_count = db.execute(
            text("SELECT COUNT(*) FROM conversations")
        ).scalar_one()
        audits = list(
            db.execute(text("SELECT metadata_json::text FROM audit_events")).scalars()
        )

    stored = " ".join([*messages, citation, feedback_comment, *audits])
    assert conversation_count == 1
    assert phone not in stored
    assert email not in stored
    assert "ĐÃ_ẨN" in stored


def test_expired_conversation_is_purged_transactionally(
    pg_session_factory: sessionmaker[Session],
) -> None:
    repository = ChatPersistenceRepository(
        retention_days=1,
        session_factory=pg_session_factory,
    )
    stored = repository.record_chat_turn(
        request_id="postgres-request-old",
        conversation_id="postgres-conversation-expired",
        consent_to_store=True,
        user_content="Câu hỏi cũ",
        assistant_content="Câu trả lời cũ",
        response_type="grounded_answer",
        data_classification="official_current",
        grounded=True,
        intent="faq",
        citations=[],
        structured_record_ids=[],
    )
    old_created = datetime.now(UTC) - timedelta(days=3)
    old_expiry = datetime.now(UTC) - timedelta(days=2)
    with pg_session_factory() as db, db.begin():
        db.execute(
            text(
                """
                UPDATE conversations
                SET created_at = :created_at, expires_at = :expires_at
                WHERE conversation_id = :conversation_id
                """
            ),
            {
                "created_at": old_created,
                "expires_at": old_expiry,
                "conversation_id": stored.conversation_id,
            },
        )
        db.execute(
            text(
                """
                UPDATE chat_messages SET created_at = :created_at
                WHERE conversation_id = :conversation_id
                """
            ),
            {
                "created_at": old_created,
                "conversation_id": stored.conversation_id,
            },
        )

    repository.record_chat_turn(
        request_id="postgres-request-purge-trigger",
        conversation_id="postgres-conversation-current",
        consent_to_store=False,
        user_content="Không lưu",
        assistant_content="Không lưu",
        response_type="non_factual",
        data_classification="non_factual",
        grounded=False,
        intent="greeting",
        citations=[],
        structured_record_ids=[],
    )
    with pg_session_factory() as db:
        assert (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM conversations
                    WHERE conversation_id = :conversation_id
                    """
                ),
                {"conversation_id": stored.conversation_id},
            ).scalar_one()
            == 0
        )
