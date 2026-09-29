"""
Notification model for push notification tracking.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, generate_ulid
from app.db.enums import DeliveryStatus, NotificationType


class Notification(Base):
    """Notification record for tracking push notifications."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("notif_"),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    incident_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Notification content
    notification_type: Mapped[NotificationType] = mapped_column(
        ENUM(NotificationType, name="notification_type_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Delivery status
    delivery_status: Mapped[DeliveryStatus] = mapped_column(
        ENUM(DeliveryStatus, name="delivery_status_enum", create_type=False, values_callable=lambda x: [e.value for e in x]),
        default=DeliveryStatus.PENDING,
    )

    # Timestamps
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # FCM message ID for tracking
    fcm_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)

    # Relationships
    user: Mapped["User"] = relationship("User")
    incident: Mapped["Incident | None"] = relationship(
        "Incident", back_populates="notifications"
    )

    __table_args__ = (
        Index("idx_notifications_user_id", "user_id"),
        Index("idx_notifications_incident_id", "incident_id"),
        Index("idx_notifications_delivery_status", "delivery_status"),
        Index("idx_notifications_created_at", "created_at"),
        Index("idx_notifications_user_status", "user_id", "delivery_status", "created_at"),
    )


# Import to avoid circular imports
from app.db.models.incident import Incident  # noqa: E402, F811
from app.db.models.user import User  # noqa: E402, F811
