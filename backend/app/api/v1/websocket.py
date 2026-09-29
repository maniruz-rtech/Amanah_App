"""
WebSocket router for real-time incident and notification updates.
"""

from fastapi import APIRouter, WebSocketException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.websockets import WebSocketHandler

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket,
    token: str = Query(...),
    db: AsyncSession = Query(dependency=get_db),
):
    """
    WebSocket endpoint for real-time updates.

    Requires JWT token as query parameter.
    Connects client to WebSocket and broadcasts events.

    Query Parameters:
        token: JWT access token

    Message Types:
        - ping: Keep-alive (responds with pong)
        - subscribe: Subscribe to channel (e.g., "user:{user_id}")
        - unsubscribe: Unsubscribe from channel

    Broadcasts:
        - notification: Push notification
        - incident_update: Incident status/location change
        - responder_assignment: New responder assignment
        - assignment_status_changed: Assignment status update
    """
    handler = WebSocketHandler(db)

    try:
        await handler.handle_connection(websocket, token)
    except Exception as e:
        raise WebSocketException(code=1011, reason=str(e))


__all__ = ["router"]
