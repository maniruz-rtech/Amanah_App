"""
ResponderStatus model for availability and location tracking.
"""

from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid


class ResponderStatus(Base):
    """Responder availability and location status."""

    __tablename__ = "responder_status"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("rstat_"),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    is_available: Mapped[bool] = mapped_column(Boolean, default=False)

    # Location (stored as lat/lng and also as PostGIS geography)
    last_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    location: Mapped[Geography | None] = mapped_column(
        # spatial_index=False — __table_args__ declares the GiST index explicitly
        # with a stable name; suppress the GeoAlchemy2 auto-index to prevent
        # `DuplicateTableError` at create_all time.
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )

    last_location_at: Mapped[datetime | None] = mapped_column(nullable=True)
    battery_level: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Track active incident count for load balancing
    active_incident_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="responder_status")

    __table_args__ = (
        Index("idx_responder_status_user_id", "user_id"),
        Index("idx_responder_status_available", "is_available"),
        # PostGIS GIST index for spatial queries
        Index("idx_responder_status_location", "location", postgresql_using="gist"),
    )


# Import to avoid circular imports
from app.db.models.user import User  # noqa: E402, F811
