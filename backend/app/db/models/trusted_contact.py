"""
TrustedContact model for emergency contact notification.
"""

from sqlalchemy import ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid


class TrustedContact(Base):
    """Trusted contact entity for emergency notifications."""

    __tablename__ = "trusted_contacts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("tc_"),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Encrypted phone number
    phone_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    relationship_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)  # 1 = highest

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="trusted_contacts")

    __table_args__ = (
        Index("idx_trusted_contacts_user_id", "user_id"),
        Index("idx_trusted_contacts_priority", "user_id", "priority"),
    )


# Import to avoid circular imports
from app.db.models.user import User  # noqa: E402, F811
