"""
Event broadcaster utilities for pushing real-time updates to clients.

Handles incident updates, notification broadcasts, and assignment notifications.
"""

from datetime import UTC, datetime

import structlog

from app.db.enums import NotificationType
from app.websockets.handlers import manager, build_incident_update_message, build_notification_message, build_assignment_message

logger = structlog.get_logger()


class EventBroadcaster:
    """Broadcasts events to WebSocket clients through channels."""

    @staticmethod
    async def broadcast_incident_created(incident: dict) -> None:
        """
        Broadcast incident creation to incident channel.

        Args:
            incident: Incident data dict
        """
        message = build_incident_update_message(
            {
                **incident,
                "event": "created",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        sent = await manager.broadcast_to_channel(
            f"incident:{incident['id']}",
            message,
        )

        logger.info(
            "incident_created_broadcast",
            incident_id=incident["id"],
            recipients=sent,
        )

    @staticmethod
    async def broadcast_incident_location_update(
        incident_id: str,
        location: dict,
    ) -> None:
        """
        Broadcast location update to incident channel.

        Args:
            incident_id: Incident ID
            location: Location data dict
        """
        message = build_incident_update_message(
            {
                "id": incident_id,
                "event": "location_updated",
                "location": location,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        sent = await manager.broadcast_to_channel(
            f"incident:{incident_id}",
            message,
        )

        logger.info(
            "incident_location_broadcast",
            incident_id=incident_id,
            recipients=sent,
        )

    @staticmethod
    async def broadcast_incident_status_change(
        incident_id: str,
        old_status: str,
        new_status: str,
    ) -> None:
        """
        Broadcast incident status change to incident channel.

        Args:
            incident_id: Incident ID
            old_status: Previous status
            new_status: New status
        """
        message = build_incident_update_message(
            {
                "id": incident_id,
                "event": "status_changed",
                "old_status": old_status,
                "new_status": new_status,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        sent = await manager.broadcast_to_channel(
            f"incident:{incident_id}",
            message,
        )

        logger.info(
            "incident_status_broadcast",
            incident_id=incident_id,
            new_status=new_status,
            recipients=sent,
        )

    @staticmethod
    async def broadcast_responder_assignment(
        incident_id: str,
        responder_user_id: str,
        assignment: dict,
    ) -> None:
        """
        Broadcast responder assignment to responder and incident channels.

        Args:
            incident_id: Incident ID
            responder_user_id: Responder user ID
            assignment: Assignment data dict
        """
        message = build_assignment_message(assignment)

        # Send to responder's personal channel
        responder_sent = await manager.broadcast_to_channel(
            f"responder:{responder_user_id}",
            message,
        )

        # Send to incident channel
        incident_sent = await manager.broadcast_to_channel(
            f"incident:{incident_id}",
            message,
        )

        logger.info(
            "responder_assignment_broadcast",
            incident_id=incident_id,
            responder_user_id=responder_user_id,
            responder_recipients=responder_sent,
            incident_recipients=incident_sent,
        )

    @staticmethod
    async def broadcast_assignment_status_change(
        assignment_id: str,
        incident_id: str,
        responder_user_id: str,
        old_status: str,
        new_status: str,
    ) -> None:
        """
        Broadcast assignment status change to responder and incident channels.

        Args:
            assignment_id: Assignment ID
            incident_id: Incident ID
            responder_user_id: Responder user ID
            old_status: Previous status
            new_status: New status
        """
        message = {
            "type": "assignment_status_changed",
            "assignment_id": assignment_id,
            "incident_id": incident_id,
            "old_status": old_status,
            "new_status": new_status,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Send to responder's personal channel
        responder_sent = await manager.broadcast_to_channel(
            f"responder:{responder_user_id}",
            message,
        )

        # Send to incident channel
        incident_sent = await manager.broadcast_to_channel(
            f"incident:{incident_id}",
            message,
        )

        logger.info(
            "assignment_status_broadcast",
            assignment_id=assignment_id,
            incident_id=incident_id,
            new_status=new_status,
            responder_recipients=responder_sent,
            incident_recipients=incident_sent,
        )

    @staticmethod
    async def broadcast_notification_to_user(
        user_id: str,
        notification: dict,
    ) -> None:
        """
        Broadcast push notification to user's WebSocket connections.

        Args:
            user_id: Target user ID
            notification: Notification data dict
        """
        message = build_notification_message(notification)

        sent = await manager.broadcast_to_user(user_id, message)

        logger.info(
            "notification_broadcast",
            user_id=user_id,
            notification_id=notification.get("id"),
            recipients=sent,
        )

    @staticmethod
    async def broadcast_incident_channel_notification(
        incident_id: str,
        notification: dict,
    ) -> None:
        """
        Broadcast notification to all subscribers of an incident channel.

        Args:
            incident_id: Incident ID
            notification: Notification data dict
        """
        message = build_notification_message(notification)

        sent = await manager.broadcast_to_channel(
            f"incident:{incident_id}",
            message,
        )

        logger.info(
            "incident_notification_broadcast",
            incident_id=incident_id,
            recipients=sent,
        )

    @staticmethod
    async def broadcast_to_incident_channel(
        incident_id: str,
        message_type: str,
        data: dict,
    ) -> None:
        """
        Broadcast generic message to incident channel.

        Args:
            incident_id: Incident ID
            message_type: Type of message
            data: Message data
        """
        message = {
            "type": message_type,
            "incident_id": incident_id,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        sent = await manager.broadcast_to_channel(
            f"incident:{incident_id}",
            message,
        )

        logger.info(
            "incident_channel_broadcast",
            incident_id=incident_id,
            message_type=message_type,
            recipients=sent,
        )

    @staticmethod
    async def broadcast_to_responder_channel(
        responder_user_id: str,
        message_type: str,
        data: dict,
    ) -> None:
        """
        Broadcast generic message to responder channel.

        Args:
            responder_user_id: Responder user ID
            message_type: Type of message
            data: Message data
        """
        message = {
            "type": message_type,
            "responder_user_id": responder_user_id,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        sent = await manager.broadcast_to_channel(
            f"responder:{responder_user_id}",
            message,
        )

        logger.info(
            "responder_channel_broadcast",
            responder_user_id=responder_user_id,
            message_type=message_type,
            recipients=sent,
        )


__all__ = ["EventBroadcaster", "manager"]
