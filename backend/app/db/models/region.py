"""
Region model.
"""

from sqlalchemy import Boolean, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid


class Region(Base):
    """Region entity for hierarchical geographic organization."""

    __tablename__ = "regions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("reg_"),
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="regions"
    )
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="region", lazy="selectin"
    )

    __table_args__ = (
        Index("idx_regions_organization_id", "organization_id"),
        Index("idx_regions_name", "name"),
        Index("idx_regions_is_active", "is_active"),
    )


# Import to avoid circular imports
from app.db.models.organization import Organization  # noqa: E402, F811
from app.db.models.user import User  # noqa: E402
