"""
WebSocket handler for real-time updates.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ValidationError

from app.core.security import verify_access_token
from app.core.exceptions import InvalidTokenError

logger = structlog.get_logger()


class WebSocketMessage(BaseModel):
    """WebSocket message format."""

    type: str
    payload: dict[str, Any] = {}


class ConnectionManager:
    """
    Manages WebSocket connections.

    Organizes connections by user_id and incident_id for targeted messaging.
    """

    def __init__(self):
        # user_id -> list of WebSocket connections
        self.user_connections: dict[str, list[WebSocket]] = {}
        # incident_id -> set of user_ids subscribed
        self.incident_subscriptions: dict[str, set[str]] = {}
        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        """Accept and register a new connection."""
        await websocket.accept()

        async with self._lock:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = []
            self.user_connections[user_id].append(websocket)

        await logger.ainfo("websocket_connected", user_id=user_id)

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """Remove a connection."""
        async with self._lock:
            if user_id in self.user_connections:
                if websocket in self.user_connections[user_id]:
                    self.user_connections[user_id].remove(websocket)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]

            # Remove from all incident subscriptions
            for incident_id, subscribers in self.incident_subscriptions.items():
                subscribers.discard(user_id)

        await logger.ainfo("websocket_disconnected", user_id=user_id)

    async def subscribe_to_incident(self, user_id: str, incident_id: str) -> None:
        """Subscribe user to incident updates."""
        async with self._lock:
            if incident_id not in self.incident_subscriptions:
                self.incident_subscriptions[incident_id] = set()
            self.incident_subscriptions[incident_id].add(user_id)

        await logger.ainfo(
            "incident_subscribed",
            user_id=user_id,
            incident_id=incident_id,
        )

    async def unsubscribe_from_incident(self, user_id: str, incident_id: str) -> None:
        """Unsubscribe user from incident updates."""
        async with self._lock:
            if incident_id in self.incident_subscriptions:
                self.incident_subscriptions[incident_id].discard(user_id)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        """Send message to all connections of a user."""
        connections = self.user_connections.get(user_id, [])

        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                await logger.awarning(
                    "send_to_user_failed",
                    user_id=user_id,
                    error=str(e),
                )

    async def broadcast_to_incident(self, incident_id: str, message: dict) -> None:
        """Broadcast message to all users subscribed to an incident."""
        subscribers = self.incident_subscriptions.get(incident_id, set())

        for user_id in subscribers:
            await self.send_to_user(user_id, message)

    async def broadcast_location_update(
        self,
        incident_id: str,
        user_id: str,
        lat: float,
        lng: float,
        accuracy_m: int | None = None,
    ) -> None:
        """Broadcast location update for an incident."""
        message = {
            "type": "location_update",
            "payload": {
                "incident_id": incident_id,
                "user_id": user_id,
                "lat": lat,
                "lng": lng,
                "accuracy_m": accuracy_m,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }
        await self.broadcast_to_incident(incident_id, message)

    async def broadcast_status_update(
        self,
        incident_id: str,
        status: str,
        actor_user_id: str | None = None,
    ) -> None:
        """Broadcast incident status update."""
        message = {
            "type": "status_update",
            "payload": {
                "incident_id": incident_id,
                "status": status,
                "actor_user_id": actor_user_id,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }
        await self.broadcast_to_incident(incident_id, message)

    async def notify_responder_accepted(
        self,
        incident_id: str,
        creator_user_id: str,
        responder_id: str,
        eta_minutes: int,
    ) -> None:
        """Notify incident creator that a responder accepted."""
        message = {
            "type": "responder_accepted",
            "payload": {
                "incident_id": incident_id,
                "responder_id": responder_id,
                "eta_minutes": eta_minutes,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }
        await self.send_to_user(creator_user_id, message)

    async def notify_responder_arrived(
        self,
        incident_id: str,
        creator_user_id: str,
        responder_id: str,
    ) -> None:
        """Notify incident creator that responder arrived."""
        message = {
            "type": "responder_arrived",
            "payload": {
                "incident_id": incident_id,
                "responder_id": responder_id,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }
        await self.send_to_user(creator_user_id, message)

    async def send_incident_assignment(
        self,
        responder_user_id: str,
        incident_id: str,
        incident_type: str,
        severity: str,
        distance_m: int | None = None,
    ) -> None:
        """Send new incident assignment to responder."""
        message = {
            "type": "incident_assigned",
            "payload": {
                "incident_id": incident_id,
                "incident_type": incident_type,
                "severity": severity,
                "distance_m": distance_m,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }
        await self.send_to_user(responder_user_id, message)


# Global connection manager instance
manager = ConnectionManager()


async def authenticate_websocket(websocket: WebSocket) -> str | None:
    """
    Authenticate WebSocket connection using token from query params.

    Returns user_id if valid, None otherwise.
    """
    token = websocket.query_params.get("token")

    if not token:
        return None

    try:
        payload = verify_access_token(token)
        return payload.get("sub")
    except InvalidTokenError:
        return None


async def handle_websocket_message(
    websocket: WebSocket,
    user_id: str,
    message: WebSocketMessage,
) -> None:
    """Handle incoming WebSocket message."""
    if message.type == "subscribe_incident":
        incident_id = message.payload.get("incident_id")
        if incident_id:
            await manager.subscribe_to_incident(user_id, incident_id)
            await websocket.send_json({
                "type": "subscribed",
                "payload": {"incident_id": incident_id},
            })

    elif message.type == "unsubscribe_incident":
        incident_id = message.payload.get("incident_id")
        if incident_id:
            await manager.unsubscribe_from_incident(user_id, incident_id)
            await websocket.send_json({
                "type": "unsubscribed",
                "payload": {"incident_id": incident_id},
            })

    elif message.type == "location_update":
        # Handle real-time location update from client
        incident_id = message.payload.get("incident_id")
        lat = message.payload.get("lat")
        lng = message.payload.get("lng")
        accuracy_m = message.payload.get("accuracy_m")

        if incident_id and lat and lng:
            await manager.broadcast_location_update(
                incident_id=incident_id,
                user_id=user_id,
                lat=lat,
                lng=lng,
                accuracy_m=accuracy_m,
            )

    elif message.type == "ping":
        await websocket.send_json({
            "type": "pong",
            "payload": {"timestamp": datetime.now(UTC).isoformat()},
        })

    else:
        await websocket.send_json({
            "type": "error",
            "payload": {"message": f"Unknown message type: {message.type}"},
        })


async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint handler.

    Connection flow:
    1. Client connects with ?token=<JWT>
    2. Server validates token and accepts connection
    3. Client can subscribe to incident updates
    4. Server pushes real-time updates
    """
    # Authenticate
    user_id = await authenticate_websocket(websocket)

    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Connect
    await manager.connect(websocket, user_id)

    try:
        while True:
            # Receive message
            data = await websocket.receive_text()

            try:
                message_data = json.loads(data)
                message = WebSocketMessage(**message_data)
                await handle_websocket_message(websocket, user_id, message)

            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": "Invalid JSON"},
                })
            except ValidationError as e:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": f"Invalid message format: {e}"},
                })

    except WebSocketDisconnect:
        await manager.disconnect(websocket, user_id)
    except Exception as e:
        await logger.aerror("websocket_error", user_id=user_id, error=str(e))
        await manager.disconnect(websocket, user_id)


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    return manager
