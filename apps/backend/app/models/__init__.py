"""SQLAlchemy model package.

Only the declarative base is exposed for now. Domain tables must be added after
official hospital data contracts are confirmed.
"""

from app.core.database import Base

__all__ = ["Base"]

