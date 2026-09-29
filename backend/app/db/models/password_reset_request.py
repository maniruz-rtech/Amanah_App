"""
PasswordResetRequest model for password reset workflow.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid
from app.db.enums import ApprovalStatus


class PasswordResetRequest(Base):
    """Password reset request requiring dual verification (OTP + Admin)."""

    __tablename__ = "password_reset_requests"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("prr_"),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Request timestamp
    requested_at: Mapped[datetime] = mapped_column(nullable=False)

    # Verification timestamps
    phone_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Admin approval
    admin_approval_status: Mapped[ApprovalStatus] = mapped_column(
        ENUM(ApprovalStatus, name="approval_status_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=ApprovalStatus.PENDING,
    )
    approved_by_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Completion
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Expiry (24 hours from request)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    approved_by: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_id])

    @property
    def is_expired(self) -> bool:
        """Check if request has expired."""
        return datetime.now(self.expires_at.tzinfo) > self.expires_at

    @property
    def is_verified(self) -> bool:
        """Check if OTP verification is complete."""
        return self.phone_verified_at is not None or self.email_verified_at is not None

    @property
    def is_approved(self) -> bool:
        """Check if admin approval is complete."""
        return self.admin_approval_status == ApprovalStatus.APPROVED

    @property
    def can_complete(self) -> bool:
        """Check if reset can be completed."""
        return self.is_verified and self.is_approved and not self.is_expired

    __table_args__ = (
        Index("idx_password_reset_requests_user_id", "user_id"),
        Index("idx_password_reset_requests_status", "admin_approval_status"),
        Index("idx_password_reset_requests_created_at", "created_at"),
    )


# Import to avoid circular imports
from app.db.models.user import User  # noqa: E402, F811
