"""
SQLAlchemy declarative base and common model utilities.
"""

from datetime import UTC, datetime
from typing import Any

import ulid
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


def generate_ulid(prefix: str = "") -> str:
    """Generate a ULID with optional prefix (e.g., 'usr_', 'inc_')."""
    return f"{prefix}{ulid.new().str}"


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    # Every `Mapped[datetime]` is TIMESTAMP WITH TIME ZONE. The application only
    # ever produces aware UTC datetimes (`datetime.now(UTC)`); a naive column
    # makes asyncpg reject them ("can't subtract offset-naive and offset-aware").
    type_annotation_map = {datetime: DateTime(timezone=True)}

    # Make tablename automatic based on class name
    @declared_attr.directive
    def __tablename__(cls) -> str:
        # Convert CamelCase to snake_case
        name = cls.__name__
        return "".join(["_" + c.lower() if c.isupper() else c for c in name]).lstrip("_") + "s"

    # Common columns
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class SoftDeleteMixin:
    """Mixin for soft delete support."""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = datetime.now(UTC)
