"""
Notification schemas.
"""

from datetime import datetime

from app.db.enums import DeliveryStatus, NotificationType
from app.schemas.common import BaseSchema


class NotificationResponse(BaseSchema):
    """Notification item."""

    id: str
    notification_type: NotificationType
    title: str
    body: str
    delivery_status: DeliveryStatus
    incident_id: str | None
    sent_at: datetime | None
    delivered_at: datetime | None
    read_at: datetime | None
    created_at: datetime


class NotificationMarkReadRequest(BaseSchema):
    """Mark notifications as read."""

    notification_ids: list[str]


class NotificationMarkReadResponse(BaseSchema):
    """Mark as read response."""

    success: bool = True
    marked_count: int


# Aliases for backward compatibility
MarkReadRequest = NotificationMarkReadRequest
MarkReadResponse = NotificationMarkReadResponse
