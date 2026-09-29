"""
EmergencyLocation model for incident location tracking.
"""

from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid
from app.db.enums import LocationSource


class EmergencyLocation(Base):
    """Emergency location data for incidents with automatic expiry."""

    __tablename__ = "emergency_locations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("loc_"),
    )
    incident_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Location data
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    # PostGIS geography point for spatial queries
    location: Mapped[Geography] = mapped_column(
        # spatial_index=False — explicit Index() in __table_args__ owns the GiST
        # index. Suppress GeoAlchemy2's auto-index so create_all doesn't error.
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=False,
    )

    source: Mapped[LocationSource] = mapped_column(
        ENUM(LocationSource, name="location_source_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=LocationSource.GPS,
    )

    # Timestamps
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Battery level at capture time
    battery_level: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident", back_populates="locations")
    user: Mapped["User"] = relationship("User")

    @property
    def is_expired(self) -> bool:
        """Check if location has expired."""
        return datetime.now(self.expires_at.tzinfo) > self.expires_at

    __table_args__ = (
        Index("idx_emergency_locations_incident_id", "incident_id"),
        Index("idx_emergency_locations_user_id", "user_id"),
        Index("idx_emergency_locations_captured_at", "captured_at"),
        # PostGIS GIST index for spatial queries
        Index("idx_emergency_locations_location", "location", postgresql_using="gist"),
    )


# Import to avoid circular imports
from app.db.models.incident import Incident  # noqa: E402, F811
from app.db.models.user import User  # noqa: E402, F811
