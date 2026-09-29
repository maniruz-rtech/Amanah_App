"""
OTP Request model for verification codes.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid
from app.db.enums import OTPChannel, OTPPurpose


class OTPRequest(Base):
    """OTP request record for phone/email verification."""

    __tablename__ = "otp_requests"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("otp_"),
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    channel: Mapped[OTPChannel] = mapped_column(
        ENUM(OTPChannel, name="otp_channel_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    purpose: Mapped[OTPPurpose] = mapped_column(
        ENUM(OTPPurpose, name="otp_purpose_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Hashed values (never store OTP or destination in plaintext)
    destination_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Timestamps
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Attempt tracking
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)

    # Relationships
    user: Mapped["User | None"] = relationship("User")

    @property
    def is_expired(self) -> bool:
        """Check if OTP has expired."""
        return datetime.now(self.expires_at.tzinfo) > self.expires_at

    @property
    def is_used(self) -> bool:
        """Check if OTP has been used."""
        return self.used_at is not None

    @property
    def is_max_attempts_exceeded(self) -> bool:
        """Check if max attempts reached."""
        return self.attempt_count >= self.max_attempts

    __table_args__ = (
        Index("idx_otp_requests_user_id", "user_id"),
        Index("idx_otp_requests_destination_hash", "destination_hash"),
        Index("idx_otp_requests_expires_at", "expires_at"),
    )


# Import to avoid circular imports
from app.db.models.user import User  # noqa: E402, F811
