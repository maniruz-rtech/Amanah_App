"""
IncidentAssignment model for responder assignment tracking.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid
from app.db.enums import AssignmentStatus


class IncidentAssignment(Base):
    """Assignment of responder to incident."""

    __tablename__ = "incident_assignments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("asgn_"),
    )
    incident_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    responder_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Status tracking
    status: Mapped[AssignmentStatus] = mapped_column(
        ENUM(AssignmentStatus, name="assignment_status_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=AssignmentStatus.PENDING,
    )

    # Timestamps
    assigned_at: Mapped[datetime] = mapped_column(nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Additional info
    eta_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident", back_populates="assignments")
    responder: Mapped["User"] = relationship("User")

    @property
    def is_active(self) -> bool:
        """Check if assignment is in an active state."""
        return self.status in {
            AssignmentStatus.PENDING,
            AssignmentStatus.ACCEPTED,
            AssignmentStatus.EN_ROUTE,
            AssignmentStatus.ARRIVED,
        }

    __table_args__ = (
        Index("idx_incident_assignments_incident_id", "incident_id"),
        Index("idx_incident_assignments_responder_id", "responder_id"),
        Index("idx_incident_assignments_status", "status"),
        Index(
            "idx_incident_assignments_incident_responder",
            "incident_id",
            "responder_id",
            unique=True,
        ),
    )


# Import to avoid circular imports
from app.db.models.incident import Incident  # noqa: E402, F811
from app.db.models.user import User  # noqa: E402, F811
