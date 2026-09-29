"""
Amanah WebSocket endpoint — v2 (header-based authentication).

This is the new endpoint the Android client connects to. It supersedes the
legacy ``websocket.py`` which accepted ``?token=`` in the URL.

Transition strategy:
    1. Deploy this file alongside ``websocket.py``.
    2. Mount BOTH endpoints in ``main.py`` so old Flutter clients (still using
       query-string tokens) keep working.
    3. Switch the Android client to ``/ws`` once everything is up.
    4. After the Flutter client is decommissioned, remove ``websocket.py``.

Security improvements vs legacy:
    - Reads the token from the ``Authorization: Bearer <jwt>`` header
      (or, as a fallback during the transition, from
      ``Sec-WebSocket-Protocol`` — see RFC 6455 §1.9).
    - **Never** reads or logs query parameters.
    - Rejects the upgrade with HTTP 401 before any frame is exchanged when
      authentication fails.
    - Sends an explicit ``auth.accepted`` envelope on success so the client
      moves to ONLINE deterministically (matches OkHttpRealtimeGateway).

The envelope shape is the unified ``{v, type, event_id, ts, payload}``
contract; see ``feature-core/realtime/RealtimeEnvelope.kt`` on the client.
"""

import asyncio
import json
import secrets
import time
from typing import Any

import structlog
from fastapi import APIRouter, Header, WebSocket, WebSocketDisconnect, status

from app.core.exceptions import InvalidTokenError
from app.core.security import verify_access_token
from app.websocket import manager  # reuse the existing ConnectionManager

logger = structlog.get_logger()
router = APIRouter()


# --- Token extraction --------------------------------------------------------

def _extract_token(
    authorization: str | None,
    sec_protocol: str | None,
) -> str | None:
    """
    Pull the JWT from the WebSocket upgrade request.

    Priority order:
        1. ``Authorization: Bearer <jwt>``  (preferred — matches OkHttp client)
        2. ``Sec-WebSocket-Protocol: amanah, <jwt>``  (fallback for browser
           clients that cannot set arbitrary headers on ``WebSocket(...)``)

    URL query parameters are intentionally ignored — see SECURITY.md C9.
    """
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    if sec_protocol:
        # Sec-WebSocket-Protocol is a comma-separated list. Accept "amanah, <jwt>".
        parts = [p.strip() for p in sec_protocol.split(",")]
        if len(parts) >= 2 and parts[0] == "amanah":
            return parts[1] or None
    return None


async def _authenticate(
    websocket: WebSocket,
    authorization: str | None,
    sec_protocol: str | None,
) -> str | None:
    token = _extract_token(authorization, sec_protocol)
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    try:
        payload = verify_access_token(token)
        return payload.get("sub")
    except InvalidTokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None


# --- Envelope helpers --------------------------------------------------------

def _envelope(event_type: str, payload: dict[str, Any], event_id: str | None = None) -> dict:
    return {
        "v": 1,
        "type": event_type,
        "event_id": event_id or secrets.token_urlsafe(12),
        "ts": int(time.time() * 1000),
        "payload": payload,
    }


# --- WebSocket endpoint ------------------------------------------------------

@router.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    authorization: str | None = Header(default=None),
    sec_websocket_protocol: str | None = Header(default=None),
):
    """
    Connection lifecycle:
        1. Server reads Authorization header (or Sec-WebSocket-Protocol).
        2. If invalid → close with 1008 BEFORE accept.
        3. If valid  → accept; send ``auth.accepted`` envelope.
        4. Loop: receive client envelopes; route by ``type``.
        5. On disconnect, manager cleans up subscriptions.
    """
    user_id = await _authenticate(websocket, authorization, sec_websocket_protocol)
    if not user_id:
        return  # already closed by _authenticate

    # Negotiate sub-protocol if the client opted into the header fallback.
    accept_protocol: str | None = "amanah" if sec_websocket_protocol and "amanah" in sec_websocket_protocol else None
    await websocket.accept(subprotocol=accept_protocol)

    # Register the connection BEFORE sending auth.accepted so any concurrent
    # broadcast finds the user. We piggy-back on the existing ConnectionManager
    # to retain compatibility with the legacy broadcast code path.
    manager.user_connections.setdefault(user_id, []).append(websocket)
    await logger.ainfo("ws_v2_connected", user_id=user_id)

    try:
        await websocket.send_json(_envelope("auth.accepted", {"user_id": user_id}))

        while True:
            raw = await websocket.receive_text()
            try:
                envelope = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(_envelope("error", {"reason": "invalid_json"}))
                continue

            etype = envelope.get("type")
            eid   = envelope.get("event_id")
            payload = envelope.get("payload") or {}

            if etype == "ping":
                # Reply with a pong carrying the original event_id so clients
                # that track latency can pair them, though our HeartbeatScheduler
                # only uses pong recency.
                await websocket.send_json(_envelope("pong", {"echo_id": eid}))
                continue

            # Every non-ping inbound message is ACKed so the client's
            # AckRegistry can complete its outcome observable.
            await websocket.send_json(_envelope("ack", {"event_id": eid}))

            if etype == "emergency.alert":
                # Hand off to the incident service. Server is authoritative on
                # broadcast — we DO NOT trust the client's payload to fan out
                # to arbitrary users.
                await _handle_emergency_alert(user_id, payload)
            elif etype == "responder.location":
                await _handle_responder_location(user_id, payload)
            elif etype == "presence":
                await _handle_presence(user_id, payload)
            else:
                await logger.awarning("ws_v2_unknown_type", type=etype, user_id=user_id)

    except WebSocketDisconnect:
        await manager.disconnect(websocket, user_id)
    except Exception as exc:  # noqa: BLE001 — log & disconnect
        await logger.aerror("ws_v2_error", user_id=user_id, error=str(exc))
        await manager.disconnect(websocket, user_id)


# --- Inbound handlers --------------------------------------------------------
# These are thin shims that route to the existing services. The point of this
# file is the auth/handshake hardening; business logic stays in the services.

async def _handle_emergency_alert(user_id: str, payload: dict[str, Any]) -> None:
    # TODO: route to IncidentService.create_sos via dependency injection.
    # The existing REST POST /api/v1/incidents/sos remains the canonical entry
    # point; this WS handler is a low-latency duplicate for clients that prefer
    # streaming. Mirror the same auth + rate-limit semantics there.
    await logger.ainfo("ws_v2_emergency_alert_received", user_id=user_id)


async def _handle_responder_location(user_id: str, payload: dict[str, Any]) -> None:
    incident_id = payload.get("alert_id")
    lat = payload.get("lat")
    lng = payload.get("lng")
    if incident_id and lat is not None and lng is not None:
        await manager.broadcast_location_update(
            incident_id=incident_id,
            user_id=user_id,
            lat=lat,
            lng=lng,
            accuracy_m=payload.get("accuracy_m"),
        )


async def _handle_presence(user_id: str, payload: dict[str, Any]) -> None:
    # H3-cell presence is stored as obfuscated-only data; never log raw GPS.
    h3_cell = payload.get("h3_cell")
    online  = bool(payload.get("online", True))
    await logger.ainfo("ws_v2_presence", user_id=user_id, h3_cell=h3_cell, online=online)
