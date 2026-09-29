"""
Device model: one row per (user, app installation).
"""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid
from app.db.enums import DevicePlatform


class Device(Base):
    """A user's registered app installation (push-token binding, session anchor).

    Identity model
    --------------
    ``device_uuid`` is the client-generated, install-scoped identifier (for the
    Android app: a random UUID created once on first launch and persisted for the
    life of the installation — see ``DeviceIdentity`` on the client). It is what
    makes registration idempotent: logging in again from the same install finds
    the same row instead of creating a new one. ``(user_id, device_uuid)`` is
    unique. ``id`` is the server-side primary key referenced by refresh tokens.

    ``is_primary`` marks the user's first active device; it is a hint for push
    routing and is never used for authorisation.
    """

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("dev_"),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_uuid: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[DevicePlatform] = mapped_column(
        ENUM(
            DevicePlatform,
            name="device_platform_enum",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    push_token: Mapped[str | None] = mapped_column(String(500), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="devices")

    __table_args__ = (
        UniqueConstraint("user_id", "device_uuid", name="uq_devices_user_device_uuid"),
        Index("idx_devices_user_id", "user_id"),
        Index("idx_devices_is_active", "is_active"),
        Index("idx_devices_push_token", "push_token"),
    )


# Import to avoid circular imports
from app.db.models.user import User  # noqa: E402, F811
