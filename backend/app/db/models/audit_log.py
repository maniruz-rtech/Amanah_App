"""
AuditLog model for immutable audit trail.
"""

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid


class AuditLog(Base):
    """Immutable audit log for all privileged actions."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("aud_"),
    )

    # Actor
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Action details
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Request context
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    # No FK to devices: audit logs are forensic and must retain the device
    # identifier even after the device row is deleted, AND must accept
    # client-supplied device_uuid values that may not have a devices row yet.
    device_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Additional metadata - use a different attribute name since 'metadata' is reserved
    audit_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Outcome
    success: Mapped[bool] = mapped_column(default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    actor: Mapped["User | None"] = relationship("User")
    # Removed Device relationship — device_id is now a free-form audit field
    # (no FK; see column definition above).

    # Note: AuditLogs are immutable - no update_at column, no update/delete operations

    __table_args__ = (
        Index("idx_audit_logs_actor_user_id", "actor_user_id"),
        Index("idx_audit_logs_action", "action"),
        Index("idx_audit_logs_resource_type", "resource_type"),
        Index("idx_audit_logs_resource_id", "resource_id"),
        Index("idx_audit_logs_created_at", "created_at"),
        Index("idx_audit_logs_actor_created", "actor_user_id", "created_at"),
    )


# Import to avoid circular imports
from app.db.models.device import Device  # noqa: E402, F811
from app.db.models.user import User  # noqa: E402, F811
