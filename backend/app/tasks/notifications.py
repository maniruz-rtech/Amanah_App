"""
Background tasks for notification dispatch and queue processing.
"""

from datetime import UTC, datetime

import structlog

from app.core.config import settings
from app.db.enums import DeliveryStatus, NotificationType
from app.db.models import Device, Notification
from app.services.notification import NotificationService
from app.tasks import celery_app

logger = structlog.get_logger()


@celery_app.task(
    name="send_notification",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def send_notification_task(self, notification_id: str) -> dict:
    """
    Background task to dispatch a notification via push providers.

    Args:
        notification_id: ID of notification to dispatch

    Returns:
        Dict with dispatch results
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker

    import asyncio

    async def _dispatch():
        # Create async session
        engine = create_async_engine(str(settings.database_url))
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Get notification
            result = await session.execute(
                select(Notification).where(Notification.id == notification_id)
            )
            notification = result.scalar_one_or_none()

            if not notification:
                logger.error(f"Notification {notification_id} not found")
                return {"success": False, "error": "Not found"}

            # Get user devices with FCM tokens
            result = await session.execute(
                select(Device).where(
                    (Device.user_id == notification.user_id)
                    & (Device.is_active == True)
                    & (Device.push_token.isnot(None))
                )
            )
            devices = result.scalars().all()

            if not devices:
                notification.delivery_status = DeliveryStatus.FAILED
                notification.error_message = "No active devices with FCM token"
                notification.sent_at = datetime.now(UTC)
                await session.flush()
                logger.warning(
                    f"No active devices for notification {notification_id}",
                    user_id=notification.user_id,
                )
                return {"success": False, "error": "No devices"}

            # Initialize service
            service = NotificationService(session)

            # Dispatch to each device
            message_ids = []
            failed_count = 0

            for device in devices:
                message_id = await service.fcm_provider.send(
                    recipient=device.push_token,
                    title=notification.title,
                    body=notification.body,
                    data={
                        "notification_id": notification.id,
                        "type": notification.notification_type.value,
                        "incident_id": notification.incident_id or "",
                    },
                )

                if message_id:
                    message_ids.append(message_id)
                    logger.info(
                        f"Notification sent to device {device.id}",
                        notification_id=notification.id,
                        message_id=message_id,
                    )
                else:
                    failed_count += 1
                    logger.warning(
                        f"Failed to send notification to device {device.id}",
                        notification_id=notification.id,
                    )

            # Update notification status
            if message_ids:
                notification.delivery_status = DeliveryStatus.SENT
                notification.fcm_message_id = message_ids[0]
                notification.sent_at = datetime.now(UTC)

                if failed_count > 0:
                    notification.error_message = f"Failed to send to {failed_count} devices"

                logger.info(
                    f"Notification {notification_id} sent successfully",
                    device_count=len(message_ids),
                    failed_count=failed_count,
                )
            else:
                notification.delivery_status = DeliveryStatus.FAILED
                notification.error_message = "Failed to send to all devices"
                notification.sent_at = datetime.now(UTC)
                notification.retry_count += 1

                logger.error(
                    f"Notification {notification_id} failed to send to all devices",
                    retry_count=notification.retry_count,
                )

            await session.flush()
            await session.commit()

            return {
                "success": message_ids,
                "failed": failed_count,
                "status": notification.delivery_status.value,
            }

    # Run async function
    try:
        from sqlalchemy.ext.asyncio import AsyncSession

        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(_dispatch())


@celery_app.task(name="process_pending_notifications")
def process_pending_notifications_task() -> dict:
    """
    Periodic task to process all pending notifications.

    Returns:
        Dict with processing results
    """

    async def _process():
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker

        engine = create_async_engine(str(settings.database_url))
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            service = NotificationService(session)

            # Get pending notifications (limit to 100 per batch)
            result = await session.execute(
                select(Notification)
                .where(Notification.delivery_status == DeliveryStatus.PENDING)
                .limit(100)
            )
            pending = result.scalars().all()

            results = {
                "total": len(pending),
                "queued": 0,
            }

            for notification in pending:
                # Queue for dispatch
                send_notification_task.apply_async(
                    args=[notification.id],
                )
                results["queued"] += 1

            logger.info(
                "Pending notifications processed",
                **results,
            )

            return results

    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    from sqlalchemy.ext.asyncio import AsyncSession

    return loop.run_until_complete(_process())


@celery_app.task(name="retry_failed_notifications")
def retry_failed_notifications_task() -> dict:
    """
    Periodic task to retry failed notifications.

    Returns:
        Dict with retry results
    """

    async def _retry():
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker

        engine = create_async_engine(str(settings.database_url))
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Get failed notifications with retry_count < 3
            result = await session.execute(
                select(Notification)
                .where(
                    (Notification.delivery_status == DeliveryStatus.FAILED)
                    & (Notification.retry_count < 3)
                )
                .limit(100)
            )
            failed = result.scalars().all()

            results = {
                "total": len(failed),
                "queued": 0,
            }

            for notification in failed:
                notification.delivery_status = DeliveryStatus.PENDING
                notification.retry_count += 1

                # Queue for dispatch
                send_notification_task.apply_async(
                    args=[notification.id],
                )
                results["queued"] += 1

            await session.flush()
            await session.commit()

            logger.info(
                "Failed notifications retried",
                **results,
            )

            return results

    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    from sqlalchemy.ext.asyncio import AsyncSession

    return loop.run_until_complete(_retry())
