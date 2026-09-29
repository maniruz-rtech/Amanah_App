"""
WebSocket handlers for real-time incident and notification updates.

Manages authenticated WebSocket connections and broadcasts events to connected clients.
"""

import json
from typing import Callable

import structlog
from fastapi import WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocket

from app.core.security import verify_access_token
from app.db.models import User

logger = structlog.get_logger()


class ConnectionManager:
    """Manages WebSocket connections and message broadcasting."""

    def __init__(self):
        """Initialize connection manager."""
        # Map of user_id -> set of connected WebSockets
        self.active_connections: dict[str, set[WebSocket]] = {}
        # Map of channel_name -> set of WebSockets
        self.channel_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        """
        Register a new WebSocket connection.

        Args:
            websocket: WebSocket connection
            user_id: Authenticated user ID
        """
        await websocket.accept()

        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()

        self.active_connections[user_id].add(websocket)

        logger.info(
            "websocket_connected",
            user_id=user_id,
            connection_count=len(self.active_connections[user_id]),
        )

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """
        Unregister a WebSocket connection.

        Args:
            websocket: WebSocket connection
            user_id: Authenticated user ID
        """
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)

            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

        # Remove from all channels
        for channel_sockets in self.channel_connections.values():
            channel_sockets.discard(websocket)

        logger.info(
            "websocket_disconnected",
            user_id=user_id,
        )

    async def broadcast_to_user(
        self,
        user_id: str,
        message: dict,
    ) -> int:
        """
        Broadcast message to all connections for a user.

        Args:
            user_id: Target user ID
            message: Message dict to send

        Returns:
            Number of connections message was sent to
        """
        if user_id not in self.active_connections:
            return 0

        disconnected = set()
        sent_count = 0

        for websocket in self.active_connections[user_id]:
            try:
                await websocket.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.warning(
                    "websocket_send_failed",
                    user_id=user_id,
                    error=str(e),
                )
                disconnected.add(websocket)

        # Clean up disconnected
        for ws in disconnected:
            self.disconnect(ws, user_id)

        return sent_count

    async def broadcast_to_channel(
        self,
        channel: str,
        message: dict,
    ) -> int:
        """
        Broadcast message to all subscribers of a channel.

        Args:
            channel: Channel name
            message: Message dict to send

        Returns:
            Number of connections message was sent to
        """
        if channel not in self.channel_connections:
            return 0

        disconnected = set()
        sent_count = 0

        for websocket in self.channel_connections[channel]:
            try:
                await websocket.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.warning(
                    "websocket_broadcast_failed",
                    channel=channel,
                    error=str(e),
                )
                disconnected.add(websocket)

        # Clean up disconnected
        for ws in disconnected:
            # Find which user owns this websocket and disconnect
            for uid, sockets in self.active_connections.items():
                if ws in sockets:
                    self.disconnect(ws, uid)
                    break

        return sent_count

    async def subscribe_to_channel(
        self,
        websocket: WebSocket,
        channel: str,
        user_id: str,
    ) -> None:
        """
        Subscribe a connection to a channel.

        Args:
            websocket: WebSocket connection
            channel: Channel name
            user_id: Authenticated user ID (for logging)
        """
        if channel not in self.channel_connections:
            self.channel_connections[channel] = set()

        self.channel_connections[channel].add(websocket)

        logger.info(
            "websocket_subscribed_to_channel",
            user_id=user_id,
            channel=channel,
            subscriber_count=len(self.channel_connections[channel]),
        )

    def unsubscribe_from_channel(
        self,
        websocket: WebSocket,
        channel: str,
        user_id: str,
    ) -> None:
        """
        Unsubscribe a connection from a channel.

        Args:
            websocket: WebSocket connection
            channel: Channel name
            user_id: Authenticated user ID (for logging)
        """
        if channel in self.channel_connections:
            self.channel_connections[channel].discard(websocket)

            logger.info(
                "websocket_unsubscribed_from_channel",
                user_id=user_id,
                channel=channel,
                subscriber_count=len(self.channel_connections[channel]),
            )


# Global connection manager instance
manager = ConnectionManager()


class WebSocketHandler:
    """Handles WebSocket connection lifecycle and message processing."""

    def __init__(self, db: AsyncSession):
        """Initialize WebSocket handler."""
        self.db = db
        self.manager = manager

    async def authenticate_websocket(
        self,
        websocket: WebSocket,
        token: str | None = None,
    ) -> User | None:
        """
        Authenticate a WebSocket connection via JWT token.

        Args:
            websocket: WebSocket connection
            token: JWT token from query parameter

        Returns:
            Authenticated User or None if authentication fails
        """
        if not token:
            logger.warning("websocket_missing_token")
            return None

        try:
            payload = verify_access_token(token)
            user_id = payload.sub

            if not user_id:
                logger.warning("websocket_invalid_token_payload")
                return None

            # Fetch user from database
            from sqlalchemy import select

            result = await self.db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user or not user.is_active:
                logger.warning("websocket_user_inactive", user_id=user_id)
                return None

            logger.info("websocket_authenticated", user_id=user_id)
            return user

        except Exception as e:
            logger.warning("websocket_auth_failed", error=str(e))
            return None

    async def handle_connection(
        self,
        websocket: WebSocket,
        token: str,
    ) -> None:
        """
        Handle a WebSocket connection with authentication and message loop.

        Args:
            websocket: WebSocket connection
            token: JWT authentication token
        """
        # Authenticate
        user = await self.authenticate_websocket(websocket, token)

        if not user:
            await websocket.close(code=4001, reason="Unauthorized")
            return

        # Register connection
        await self.manager.connect(websocket, user.id)

        try:
            # Auto-subscribe to user's personal channel
            await self.manager.subscribe_to_channel(
                websocket,
                f"user:{user.id}",
                user.id,
            )

            # Subscribe responders to responder channels
            if user.responder_status:
                await self.manager.subscribe_to_channel(
                    websocket,
                    f"responder:{user.id}",
                    user.id,
                )

            # Message loop
            while True:
                data = await websocket.receive_json()
                await self._handle_message(websocket, user, data)

        except WebSocketDisconnect:
            logger.info("websocket_disconnected_client", user_id=user.id)
            self.manager.disconnect(websocket, user.id)

        except Exception as e:
            logger.error("websocket_error", user_id=user.id, error=str(e))
            self.manager.disconnect(websocket, user.id)

    async def _handle_message(
        self,
        websocket: WebSocket,
        user: User,
        data: dict,
    ) -> None:
        """
        Handle incoming WebSocket message.

        Args:
            websocket: WebSocket connection
            user: Authenticated user
            data: Message data
        """
        message_type = data.get("type")

        if message_type == "ping":
            await websocket.send_json({"type": "pong"})

        elif message_type == "subscribe":
            channel = data.get("channel")
            if channel and channel.startswith(f"user:{user.id}"):
                # Only allow subscribing to own user channel
                await self.manager.subscribe_to_channel(
                    websocket,
                    channel,
                    user.id,
                )
                await websocket.send_json(
                    {
                        "type": "subscribed",
                        "channel": channel,
                    }
                )

        elif message_type == "unsubscribe":
            channel = data.get("channel")
            if channel and channel.startswith(f"user:{user.id}"):
                self.manager.unsubscribe_from_channel(
                    websocket,
                    channel,
                    user.id,
                )
                await websocket.send_json(
                    {
                        "type": "unsubscribed",
                        "channel": channel,
                    }
                )

        else:
            logger.warning(
                "websocket_unknown_message_type",
                user_id=user.id,
                message_type=message_type,
            )


# Message builders for different event types
def build_notification_message(notification: dict) -> dict:
    """Build notification message for WebSocket."""
    return {
        "type": "notification",
        "notification": notification,
    }


def build_incident_update_message(incident: dict) -> dict:
    """Build incident update message for WebSocket."""
    return {
        "type": "incident_update",
        "incident": incident,
    }


def build_assignment_message(assignment: dict) -> dict:
    """Build assignment message for WebSocket."""
    return {
        "type": "responder_assignment",
        "assignment": assignment,
    }
