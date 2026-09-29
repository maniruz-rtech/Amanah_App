"""
IncidentEvent model for audit trail.
"""

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid
from app.db.enums import IncidentEventType


class IncidentEvent(Base):
    """Immutable event record for incident audit trail."""

    __tablename__ = "incident_events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("evt_"),
    )
    incident_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    event_type: Mapped[IncidentEventType] = mapped_column(
        ENUM(IncidentEventType, name="incident_event_type_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    event_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident", back_populates="events")
    actor: Mapped["User | None"] = relationship("User")

    # Note: IncidentEvents are immutable - no update/delete operations should be allowed

    __table_args__ = (
        Index("idx_incident_events_incident_id", "incident_id"),
        Index("idx_incident_events_created_at", "created_at"),
        Index("idx_incident_events_event_type", "event_type"),
    )


# Import to avoid circular imports
from app.db.models.incident import Incident  # noqa: E402, F811
from app.db.models.user import User  # noqa: E402, F811
