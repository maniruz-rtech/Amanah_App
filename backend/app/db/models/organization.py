"""
Organization model.
"""

from sqlalchemy import Boolean, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid


class Organization(Base):
    """Organization entity representing a tenant/community."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("org_"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    regions: Mapped[list["Region"]] = relationship(
        "Region", back_populates="organization", lazy="selectin"
    )
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="organization", lazy="selectin"
    )

    __table_args__ = (
        Index("idx_organizations_name", "name"),
        Index("idx_organizations_is_active", "is_active"),
    )


# Import here to avoid circular imports
from app.db.models.region import Region  # noqa: E402
from app.db.models.user import User  # noqa: E402
