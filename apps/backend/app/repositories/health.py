"""Health-check data access."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

EXPECTED_DATABASE_REVISION = "0001_initial_schema"


class DatabaseHealthRepository:
    """Repository for database readiness checks."""

    def __init__(self, db: Session):
        self.db = db

    def ping(self) -> bool:
        """Return true when PostgreSQL responds to SELECT 1."""

        return self.db.execute(text("SELECT 1")).scalar_one() == 1

    def migration_is_current(
        self,
        expected_revision: str = EXPECTED_DATABASE_REVISION,
    ) -> bool:
        """Return true only when Alembic reports the release schema revision."""

        revision = self.db.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
        return revision == expected_revision

