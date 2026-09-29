"""
Notification service for managing and sending notifications.

Supports abstracted notification dispatch with Firebase Cloud Messaging (FCM),
SMS (Twilio), and email providers.
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.enums import enum_value
from app.db.enums import DeliveryStatus, NotificationType
from app.db.models import Notification
from app.repositories import DeviceRepository, NotificationRepository
from app.schemas.notification import NotificationResponse

logger = structlog.get_logger()


class NotificationProvider(ABC):
    """Abstract base class for notification providers."""

    @abstractmethod
    async def send(
        self,
        recipient: str,
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> str | None:
        """
        Send a notification through the provider.

        Args:
            recipient: Target recipient (device token, phone number, email, etc.)
            title: Notification title
            body: Notification body/message
            data: Optional metadata to include with notification

        Returns:
            Provider message ID or None if send failed
        """
        pass


class FCMProvider(NotificationProvider):
    """Firebase Cloud Messaging notification provider."""

    def __init__(self):
        """Initialize FCM provider."""
        self.enabled = settings.fcm_enabled
        self.credentials_path = settings.firebase_credentials_path
        self._init_client()

    def _init_client(self) -> None:
        """Initialize Firebase admin client if enabled."""
        if not self.enabled:
            return

        try:
            import firebase_admin
            from firebase_admin import credentials, messaging

            self.messaging = messaging

            # Load credentials
            if self.credentials_path:
                cred = credentials.Certificate(self.credentials_path)
                firebase_admin.initialize_app(cred)
        except ImportError:
            self.enabled = False
        except Exception:
            self.enabled = False

    async def send(
        self,
        recipient: str,
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> str | None:
        """Send notification via Firebase Cloud Messaging."""
        if not self.enabled:
            return None

        try:
            message = self.messaging.Message(
                notification=self.messaging.Notification(title=title, body=body),
                data=data or {},
                token=recipient,
            )
            # firebase-admin's send() is synchronous network I/O — keep it off the loop.
            return await asyncio.to_thread(self.messaging.send, message)
        except Exception:
            return None


class SMSProvider(NotificationProvider):
    """SMS notification provider using Twilio."""

    def __init__(self):
        """Initialize SMS provider."""
        self.enabled = settings.sms_enabled
        self.account_sid = settings.twilio_account_sid
        self.auth_token = settings.twilio_auth_token
        self.phone_number = settings.twilio_phone_number
        self._init_client()

    def _init_client(self) -> None:
        """Initialize Twilio client if enabled."""
        if not self.enabled or not (
            self.account_sid and self.auth_token and self.phone_number
        ):
            self.enabled = False
            return

        try:
            from twilio.rest import Client

            self.client = Client(self.account_sid, self.auth_token)
        except ImportError:
            self.enabled = False
        except Exception:
            self.enabled = False

    async def send(
        self,
        recipient: str,
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> str | None:
        """Send SMS via Twilio."""
        if not self.enabled:
            return None

        try:
            # Format message (title + body for SMS)
            message_text = f"{title}\n{body}"

            message = self.client.messages.create(
                body=message_text,
                from_=self.phone_number,
                to=recipient,
            )
            return message.sid
        except Exception:
            return None


class EmailProvider(NotificationProvider):
    """Email notification provider using SMTP."""

    async def send(
        self,
        recipient: str,
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> str | None:
        """Send email notification."""
        # Implementation depends on email provider choice
        # For now, placeholder that does not send
        return None


class NotificationService:
    """Service for notification operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_repo = NotificationRepository(db)
        self.device_repo = DeviceRepository(db)

        # Initialize providers
        self.fcm_provider = FCMProvider()
        self.sms_provider = SMSProvider()
        self.email_provider = EmailProvider()

    async def create_notification(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        body: str,
        incident_id: str | None = None,
    ) -> Notification:
        """Create a new notification."""
        notification = await self.notification_repo.create_notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            body=body,
            incident_id=incident_id,
        )

        await logger.ainfo(
            "notification_created",
            notification_id=notification.id,
            user_id=user_id,
            type=notification_type,
        )

        return notification

    async def get_user_notifications(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        unread_only: bool = False,
    ) -> tuple[list[NotificationResponse], int]:
        """Get notifications for a user."""
        notifications, total = await self.notification_repo.get_user_notifications(
            user_id=user_id,
            skip=skip,
            limit=limit,
            unread_only=unread_only,
        )

        return [NotificationResponse.model_validate(n) for n in notifications], total

    async def mark_read(
        self,
        user_id: str,
        notification_ids: list[str],
    ) -> int:
        """Mark notifications as read."""
        count = await self.notification_repo.mark_read(
            notification_ids=notification_ids,
            user_id=user_id,
        )

        await logger.ainfo(
            "notifications_marked_read",
            user_id=user_id,
            count=count,
        )

        return count

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user."""
        # Get all unread notification IDs
        notifications, _ = await self.notification_repo.get_user_notifications(
            user_id=user_id,
            unread_only=True,
            limit=1000,
        )

        if not notifications:
            return 0

        notification_ids = [n.id for n in notifications]
        count = await self.notification_repo.mark_read(
            notification_ids=notification_ids,
            user_id=user_id,
        )

        await logger.ainfo(
            "all_notifications_marked_read",
            user_id=user_id,
            count=count,
        )

        return count

    async def send_push_notification(
        self,
        notification: Notification,
    ) -> bool:
        """Send a notification to every active device of its user via FCM.

        Succeeds when at least one device accepted the message; the notification
        is then marked SENT with the provider's message id. Otherwise it is marked
        FAILED (with the reason) and becomes eligible for
        :meth:`retry_failed_notifications` until its retry budget is spent.
        """
        devices = await self.device_repo.get_user_devices(notification.user_id)
        active_devices = [d for d in devices if d.is_active and d.push_token]

        if not active_devices:
            await self.notification_repo.mark_failed(
                notification_id=notification.id,
                error_message="No active devices with a push token",
            )
            return False

        data = {
            "notification_id": notification.id,
            "type": enum_value(notification.notification_type),
            "incident_id": notification.incident_id or "",
        }
        message_id: str | None = None
        for device in active_devices:
            try:
                sent_id = await self.fcm_provider.send(
                    recipient=device.push_token,
                    title=notification.title,
                    body=notification.body,
                    data=data,
                )
            except Exception as exc:  # provider errors must not abort the batch
                await logger.awarning(
                    "push_notification_device_failed",
                    notification_id=notification.id,
                    device_id=device.id,
                    error=str(exc),
                )
                continue
            if sent_id and message_id is None:
                message_id = sent_id

        if message_id is None:
            await self.notification_repo.mark_failed(
                notification_id=notification.id,
                error_message="FCM did not accept the message (disabled or all sends failed)",
            )
            await logger.aerror("push_notification_failed", notification_id=notification.id)
            return False

        await self.notification_repo.mark_sent(
            notification_id=notification.id, fcm_message_id=message_id
        )
        await logger.ainfo(
            "push_notification_sent",
            notification_id=notification.id,
            device_count=len(active_devices),
        )
        return True

    async def dispatch_to_user(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        body: str,
        incident_id: str | None = None,
    ) -> Notification:
        """Create a notification and push it to the user's devices immediately."""
        notification = await self.create_notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            body=body,
            incident_id=incident_id,
        )
        await self.send_push_notification(notification)
        await self.db.refresh(notification)
        return notification

    async def mark_delivered(self, notification_id: str) -> Notification | None:
        """Record delivery confirmation (e.g. client ack) for a notification."""
        return await self.notification_repo.mark_delivered(notification_id)

    async def retry_failed_notifications(self, limit: int = 100) -> int:
        """Re-attempt FAILED notifications that still have retry budget; returns attempts."""
        failed = await self.notification_repo.get_failed_notifications(limit=limit)
        for notification in failed:
            await self.send_push_notification(notification)
        return len(failed)

    async def get_pending_notifications(
        self,
        limit: int = 100,
    ) -> list[Notification]:
        """Get pending notifications for batch sending."""
        return await self.notification_repo.get_pending_notifications(limit=limit)

    async def process_pending_notifications(self) -> dict:
        """Process all pending notifications (for worker task)."""
        pending = await self.get_pending_notifications()

        results = {
            "total": len(pending),
            "sent": 0,
            "failed": 0,
        }

        for notification in pending:
            success = await self.send_push_notification(notification)
            if success:
                results["sent"] += 1
            else:
                results["failed"] += 1

        await logger.ainfo(
            "pending_notifications_processed",
            **results,
        )

        return results
