"""
Notification and audit log repositories.
"""

from datetime import UTC, datetime

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import generate_ulid
from app.db.enums import DeliveryStatus, NotificationType
from app.db.models import AuditLog, Notification, TrustedContact
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    """Repository for Notification operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(Notification, db)

    async def create_notification(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        body: str,
        incident_id: str | None = None,
    ) -> Notification:
        """Create a notification."""
        notification = Notification(
            id=generate_ulid("notif_"),
            user_id=user_id,
            incident_id=incident_id,
            notification_type=notification_type,
            title=title,
            body=body,
            delivery_status=DeliveryStatus.PENDING,
        )
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)
        return notification

    async def mark_sent(
        self,
        notification_id: str,
        fcm_message_id: str | None = None,
    ) -> Notification | None:
        """Mark notification as sent."""
        notification = await self.get_by_id(notification_id)
        if notification:
            notification.delivery_status = DeliveryStatus.SENT
            notification.sent_at = datetime.now(UTC)
            notification.fcm_message_id = fcm_message_id
            await self.db.flush()
        return notification

    async def mark_delivered(self, notification_id: str) -> Notification | None:
        """Mark notification as delivered."""
        notification = await self.get_by_id(notification_id)
        if notification:
            notification.delivery_status = DeliveryStatus.DELIVERED
            notification.delivered_at = datetime.now(UTC)
            await self.db.flush()
        return notification

    async def mark_failed(
        self,
        notification_id: str,
        error_message: str,
    ) -> Notification | None:
        """Mark notification as failed."""
        notification = await self.get_by_id(notification_id)
        if notification:
            notification.delivery_status = DeliveryStatus.FAILED
            notification.error_message = error_message
            notification.retry_count += 1
            await self.db.flush()
        return notification

    async def mark_read(self, notification_ids: list[str], user_id: str) -> int:
        """Mark notifications as read."""
        result = await self.db.execute(
            update(Notification).execution_options(synchronize_session="fetch")
            .where(
                and_(
                    Notification.id.in_(notification_ids),
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
            .values(
                delivery_status=DeliveryStatus.READ,
                read_at=datetime.now(UTC),
            )
        )
        await self.db.flush()
        return result.rowcount  # type: ignore

    async def get_user_notifications(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]:
        """Get notifications for a user."""
        filters = [Notification.user_id == user_id]

        if unread_only:
            filters.append(Notification.read_at.is_(None))

        query = (
            select(Notification)
            .where(and_(*filters))
            .order_by(Notification.created_at.desc())
        )

        # Count
        count_query = select(func.count(Notification.id)).where(and_(*filters))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginate
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        notifications = list(result.scalars().all())

        return notifications, total

    async def get_pending_notifications(self, limit: int = 100) -> list[Notification]:
        """Get pending notifications for sending."""
        result = await self.db.execute(
            select(Notification)
            .where(Notification.delivery_status == DeliveryStatus.PENDING)
            .order_by(Notification.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_failed_notifications(self, limit: int = 100) -> list[Notification]:
        """Get failed notifications for retry."""
        result = await self.db.execute(
            select(Notification)
            .where(
                and_(
                    Notification.delivery_status == DeliveryStatus.FAILED,
                    Notification.retry_count < 3,
                )
            )
            .order_by(Notification.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications for user."""
        result = await self.db.execute(
            select(func.count(Notification.id)).where(
                and_(
                    Notification.user_id == user_id,
                    Notification.delivery_status != DeliveryStatus.READ,
                )
            )
        )
        return result.scalar() or 0


class AuditLogRepository(BaseRepository[AuditLog]):
    """Repository for AuditLog operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(AuditLog, db)

    async def log_action(
        self,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        actor_user_id: str | None = None,
        device_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        metadata: dict | None = None,
        description: str | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        # Older deployments keep audit_logs.device_id as VARCHAR(32).
        # Normalize incoming UUID-like identifiers to avoid runtime 500s.
        normalized_device_id = None
        if device_id:
            normalized_device_id = device_id.replace("-", "")[:32]

        log = AuditLog(
            id=generate_ulid("aud_"),
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            device_id=normalized_device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            metadata=metadata,
            description=description,
            success=success,
            error_message=error_message,
        )
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log

    async def search_logs(
        self,
        actor_user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[AuditLog], int]:
        """Search audit logs with filters."""
        filters = []

        if actor_user_id:
            filters.append(AuditLog.actor_user_id == actor_user_id)
        if action:
            filters.append(AuditLog.action == action)
        if resource_type:
            filters.append(AuditLog.resource_type == resource_type)
        if resource_id:
            filters.append(AuditLog.resource_id == resource_id)
        if date_from:
            filters.append(AuditLog.created_at >= date_from)
        if date_to:
            filters.append(AuditLog.created_at <= date_to)

        query = select(AuditLog)
        if filters:
            query = query.where(and_(*filters))
        query = query.order_by(AuditLog.created_at.desc())

        # Count
        count_query = select(func.count(AuditLog.id))
        if filters:
            count_query = count_query.where(and_(*filters))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginate
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        return logs, total


class TrustedContactRepository(BaseRepository[TrustedContact]):
    """Repository for TrustedContact operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(TrustedContact, db)

    async def get_user_contacts(self, user_id: str) -> list[TrustedContact]:
        """Get all trusted contacts for a user."""
        result = await self.db.execute(
            select(TrustedContact)
            .where(TrustedContact.user_id == user_id)
            .order_by(TrustedContact.priority)
        )
        return list(result.scalars().all())

    async def create_contact(
        self,
        user_id: str,
        name: str,
        phone_encrypted: bytes,
        relationship: str | None = None,
        priority: int = 1,
    ) -> TrustedContact:
        """Create a trusted contact."""
        contact = TrustedContact(
            id=generate_ulid("tc_"),
            user_id=user_id,
            name=name,
            phone_encrypted=phone_encrypted,
            relationship_type=relationship,
            priority=priority,
        )
        self.db.add(contact)
        await self.db.flush()
        await self.db.refresh(contact)
        return contact

    async def count_user_contacts(self, user_id: str) -> int:
        """Count user's trusted contacts."""
        return await self.count(user_id=user_id)
