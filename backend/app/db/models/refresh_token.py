"""
RefreshToken model for token tracking and rotation.
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid


class RefreshToken(Base):
    """Refresh token record for tracking and rotation."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("rtok_"),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Token identifier (JTI in JWT)
    jti: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Timestamps
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Status
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    # Rotation tracking (points to the token that replaced this one)
    replaced_by_jti: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")
    device: Mapped["Device | None"] = relationship("Device")

    @property
    def is_expired(self) -> bool:
        """Check if token has expired."""
        return datetime.now(UTC) > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if token is still valid (not revoked, not expired)."""
        return not self.is_revoked and not self.is_expired

    __table_args__ = (
        Index("idx_refresh_tokens_user_id", "user_id"),
        Index("idx_refresh_tokens_device_id", "device_id"),
        Index("idx_refresh_tokens_jti", "jti"),
        Index("idx_refresh_tokens_expires_at", "expires_at"),
    )


# Import to avoid circular imports
from app.db.models.device import Device  # noqa: E402, F811
from app.db.models.user import User  # noqa: E402, F811
