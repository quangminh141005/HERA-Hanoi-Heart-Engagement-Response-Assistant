"""Fast unit checks for the PostgreSQL booking repository contract."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.booking.repository import BookingRepository, _advisory_lock_key
from app.core.errors import HeraApiError
from sqlalchemy.exc import SQLAlchemyError


def _repository(**overrides) -> BookingRepository:
    values = {
        "hold_token_secret": "unit-test-secret-0123456789abcdef",
        "hold_ttl_seconds": 300,
        "max_active_holds_per_owner": 2,
    }
    values.update(overrides)
    return BookingRepository(**values)


def test_owner_advisory_key_is_deterministic_signed_bigint() -> None:
    first = _advisory_lock_key("a" * 64)
    second = _advisory_lock_key("a" * 64)

    assert first == second
    assert -(2**63) <= first < 2**63
    assert first != _advisory_lock_key("b" * 64)


def test_hold_token_is_deterministic_but_owner_scoped() -> None:
    repository = _repository()

    first = repository._derive_hold_token("HOLD-ONE", "owner-a")
    replay = repository._derive_hold_token("HOLD-ONE", "owner-a")
    another_owner = repository._derive_hold_token("HOLD-ONE", "owner-b")

    assert first == replay
    assert first != another_owner
    assert "unit-test-secret" not in first


def test_database_failure_returns_stable_retryable_error() -> None:
    def unavailable_session():
        raise SQLAlchemyError("synthetic database failure")

    repository = _repository(session_factory=unavailable_session)

    with pytest.raises(HeraApiError) as error:
        repository.reference_date()

    assert error.value.code == "BOOKING_UNAVAILABLE"
    assert error.value.status_code == 503
    assert error.value.retryable is True
    assert "synthetic" not in str(error.value)


def test_repository_uses_postgres_locks_and_has_no_sqlite_fallback() -> None:
    source = Path(__file__).resolve().parents[1] / "app" / "booking" / "repository.py"
    implementation = source.read_text(encoding="utf-8")

    assert "pg_advisory_xact_lock" in implementation
    assert "FOR UPDATE OF bs" in implementation
    assert "FOR UPDATE" in implementation
    assert "sqlite3" not in implementation
    assert "STRUCTURED_DB_PATH" not in implementation
