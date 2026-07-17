"""Health-check data access."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


class DatabaseHealthRepository:
    """Repository for database readiness checks."""

    def __init__(self, db: Session):
        self.db = db

    def ping(self) -> bool:
        """Return true when PostgreSQL responds to SELECT 1."""

        return self.db.execute(text("SELECT 1")).scalar_one() == 1

