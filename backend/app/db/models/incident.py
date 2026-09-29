"""
Incident model for emergency alerts.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, generate_ulid
from app.db.enums import IncidentSeverity, IncidentStatus, IncidentType


class Incident(Base, SoftDeleteMixin):
    """Incident entity for SOS alerts and emergencies."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("inc_"),
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    region_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("regions.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Incident details
    incident_type: Mapped[IncidentType] = mapped_column(
        ENUM(IncidentType, name="incident_type_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=IncidentType.SOS,
    )
    severity: Mapped[IncidentSeverity] = mapped_column(
        ENUM(IncidentSeverity, name="incident_severity_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=IncidentSeverity.HIGH,
    )
    status: Mapped[IncidentStatus] = mapped_column(
        ENUM(IncidentStatus, name="incident_status_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=IncidentStatus.BROADCASTING,
    )
    silent_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Cancellation details
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    region: Mapped["Region"] = relationship("Region")
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])

    locations: Mapped[list["EmergencyLocation"]] = relationship(
        "EmergencyLocation",
        back_populates="incident",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    assignments: Mapped[list["IncidentAssignment"]] = relationship(
        "IncidentAssignment",
        back_populates="incident",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    events: Mapped[list["IncidentEvent"]] = relationship(
        "IncidentEvent",
        back_populates="incident",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="IncidentEvent.created_at",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification",
        back_populates="incident",
        lazy="selectin",
    )

    @property
    def is_active(self) -> bool:
        """Check if incident is in an active state."""
        from app.db.enums import is_active_status
        return is_active_status(self.status)

    @property
    def latest_location(self) -> "EmergencyLocation | None":
        """Get the most recent location update."""
        if not self.locations:
            return None
        return max(self.locations, key=lambda loc: loc.captured_at)

    @property
    def accepted_responders(self) -> list["IncidentAssignment"]:
        """Get assignments where responder has accepted."""
        from app.db.enums import AssignmentStatus
        return [a for a in self.assignments if a.status == AssignmentStatus.ACCEPTED]

    __table_args__ = (
        Index("idx_incidents_organization_id", "organization_id"),
        Index("idx_incidents_region_id", "region_id"),
        Index("idx_incidents_created_by", "created_by_id"),
        Index("idx_incidents_status", "status"),
        Index("idx_incidents_created_at", "created_at"),
        Index("idx_incidents_status_created", "status", "created_at"),
    )


# Import to avoid circular imports
from app.db.models.emergency_location import EmergencyLocation  # noqa: E402
from app.db.models.incident_assignment import IncidentAssignment  # noqa: E402
from app.db.models.incident_event import IncidentEvent  # noqa: E402
from app.db.models.notification import Notification  # noqa: E402
from app.db.models.organization import Organization  # noqa: E402, F811
from app.db.models.region import Region  # noqa: E402, F811
from app.db.models.user import User  # noqa: E402, F811
