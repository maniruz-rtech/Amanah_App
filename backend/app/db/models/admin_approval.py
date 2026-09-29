"""
AdminApproval model for generic approval workflow.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid
from app.db.enums import ApprovalRequestType, ApprovalStatus


class AdminApproval(Base):
    """Generic approval record for admin-controlled workflows."""

    __tablename__ = "admin_approvals"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("aprv_"),
    )

    # Request details
    request_type: Mapped[ApprovalRequestType] = mapped_column(
        ENUM(ApprovalRequestType, name="approval_request_type_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    request_ref_id: Mapped[str] = mapped_column(String(36), nullable=False)  # Foreign ref

    # Requester
    requested_by_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Reviewer
    reviewed_by_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Status
    status: Mapped[ApprovalStatus] = mapped_column(
        ENUM(ApprovalStatus, name="approval_status_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=ApprovalStatus.PENDING,
    )

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    requested_by: Mapped["User"] = relationship("User", foreign_keys=[requested_by_id])
    reviewed_by: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by_id])

    __table_args__ = (
        Index("idx_admin_approvals_request_type", "request_type"),
        Index("idx_admin_approvals_status", "status"),
        Index("idx_admin_approvals_requested_by", "requested_by_id"),
        Index("idx_admin_approvals_request_ref", "request_type", "request_ref_id"),
    )


# Import to avoid circular imports
from app.db.models.user import User  # noqa: E402, F811
