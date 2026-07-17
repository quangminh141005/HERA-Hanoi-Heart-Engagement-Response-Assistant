"""Generic repository contracts."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session


class Repository(Protocol):
    """Minimal repository interface backed by a SQLAlchemy session."""

    db: Session

