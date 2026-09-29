# Realtime Incident Flow

The REST path **persists**. The WebSocket path **distributes**. This
document covers the distribution side end-to-end.

## Stream topology

```
Victim's device                Server                 Responder devices
───────────────                ──────                 ─────────────────

POST /incidents/sos
   ──────────────►   IncidentService.create_sos
                     INSERT incidents + ...
                     fanout: broadcast emergency.alert
                       to clients in H3 k-ring
                                          ─────────────► (WS)
                                                          OkHttpRealtimeGateway
                                                          incoming → EmergencyAlertEngine
                                                          UI surfaces incoming overlay

POST /incidents/{id}/location              Responder devices
   ──────────────►   IncidentService.add_location
                     INSERT emergency_locations
                     broadcast responder.location
                                          ─────────────► (WS)
                                                          UI updates responder marker
```

## Inbound delivery path (client side)

```
WSS wire frame (JSON envelope)
   │
   ▼
OkHttpWebSocketListener.onMessage(text)
   │
   ▼
OkHttpRealtimeGateway.onIncomingPayload(generation, text)
   │   1. Decode envelope (Gson → RealtimeEnvelope)
   │   2. Dedup by event_id (EventDedup LRU)
   │   3. RealtimeEventParser.parse(envelope) → sealed RealtimeEvent
   │   4. Internal events (Pong, Ack, AuthAccepted, AuthRejected)
   │      handled inline; everything else pushed to incomingSubject
   │
   ▼
gateway.incoming: Observable<RealtimeEvent>
   │
   ▼
UserDashboardInteractor.initializeUser → gateway.incoming.subscribe { ... }
   │
   ▼
when (event) is …
   ├─ RealtimeEvent.EmergencyAlert    → engine.onIncomingAlert(...)
   ├─ RealtimeEvent.ResponderLocation → engine.onResponderLocationUpdate(...)
   └─ (others)                         → routed to sibling interactors / admin tab
```

## Event taxonomy

Defined in [feature-core/realtime/RealtimeEnvelope.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/realtime/RealtimeEnvelope.kt):

```kotlin
sealed class RealtimeEvent {
    data class Ack(val eventId: String)            // server confirms our send
    data class Pong(val timestampMs: Long)         // heartbeat reply
    object AuthAccepted                            // gateway moves to ONLINE
    data class AuthRejected(val message: String)   // terminal AUTH_REJECTED
    data class EmergencyAlert(alertId, victimId, lat, lng, h3Cell, status, kRing, serverTsMs)
    data class ResponderLocation(responderId, alertId, lat, lng, etaSeconds?, serverTsMs)
    data class AdminNotification(notificationType, targetUserId?, message, serverTsMs)
    data class Unknown(type, raw)                  // future-proof: never crash
}
```

Adding a new event type:

1. Add sealed subclass.
2. Add `EventTypes.<NEW>` constant.
3. Add branch in `RealtimeEventParser.parse`.
4. Add branch in `UserDashboardInteractor` (or relevant interactor) — Kotlin's
   exhaustive `when` forces this at compile time.

## Acknowledgement protocol

Every non-`ping` envelope sent by the client receives an `ack` from the
server:

```json
client → { "v":1, "type":"emergency.alert", "event_id":"e1", "ttl_ms":60000, ... }
server → { "v":1, "type":"ack",             "event_id":"...",
            "payload":{"event_id":"e1"} }
```

`AckRegistry` exposes a `SendOutcome` observable per `event_id`:

- **Acknowledged(eventId)** on `ack`.
- **Failed(eventId, "ttl expired")** if the envelope expires in the
  `OutboundQueue` before delivery.
- **Failed(eventId, "disconnected")** if the gateway disconnects with the
  envelope still pending.

In the current MVP the trigger uses REST, so ACKs are only relevant for
post-trigger envelopes (presence, responder location). The infrastructure
is fully wired and tested in `OkHttpRealtimeGateway`.

## Duplicate-event protection

Reconnect can replay events the client already saw (at-least-once delivery
semantics). `EventDedup` (LRU 512) silently drops duplicates by
`event_id`:

```kotlin
if (!eventDedup.firstSeen(envelope.eventId)) {
    logger("dedup drop ${envelope.type}/${envelope.eventId}")
    return
}
```

ACK and PONG are intentionally exempt — they're transport signals, not
business events.

## Reconnect synchronisation

When the gateway transitions Online → Reconnecting → Online, the client
needs to catch up on any events it missed during the outage. Today:

- The server holds no per-client replay log; it broadcasts live only.
- After reconnect, the UI's "active incident" state is pulled from
  `GET /incidents/{id}` via REST (the canonical source of truth).
- New events resume real-time.

For perfect at-most-once-with-replay, a future iteration will add a
server-side cursor (`event_id_high_watermark`) that the client passes on
WS reconnect; the server replays everything after that cursor. Tracked
in MVP_COMPLETION_CHECKLIST.

## Cancellation events

```
admin force-resolve (AdminAlertDetail)
  → AdminRepository.resolveIncident(id, "admin_force_resolved")
  → POST /incidents/{id}/resolve
  → backend INSERT incident_events + UPDATE incidents.status
  → backend broadcasts emergency.alert with status="resolved"
  → victim's gateway.incoming → EmergencyEvent.EmergencyAlert(status="resolved")
  → Engine.onIncomingAlert sees status=RESOLVED → emits feature.accept(ResolveAlert)
  → UI overlay closes
```

## Reliability primitives (recap)

| Component | File |
|---|---|
| FSM | [RealtimeConnectionState.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/realtime/RealtimeConnectionState.kt) |
| Reconnect schedule | [ReconnectStrategy.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/realtime/ReconnectStrategy.kt) |
| Heartbeat | [HeartbeatScheduler.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/realtime/HeartbeatScheduler.kt) |
| Outbound queue (durable) | [DurableOutboundQueue.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/realtime/DurableOutboundQueue.kt) |
| Acks | [AckRegistry.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/realtime/AckRegistry.kt) |
| Dedup | [EventDedup.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/realtime/EventDedup.kt) |
| Foreground bridge | [AppForegroundObserver.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/realtime/AppForegroundObserver.kt) |

## Test plan

| Scenario | How to test |
|---|---|
| Reconnect during emergency | `iptables -A OUTPUT -p tcp --dport 8000 -j DROP` for 5 s; verify Reconnecting → Online → incoming events resume |
| Heartbeat dead-server detect | Block PONG response on backend; verify gateway closes socket after 35 s |
| Duplicate inbound event | Send same `event_id` twice via test harness; verify `EventDedup` drops second |
| WS 401 → refresh → reconnect | Revoke access token mid-session; verify single-shot refresh attempt before terminal AUTH_REJECTED |
| TTL expiration | Trigger SOS while offline; wait 60s; reconnect; verify SendOutcome.Failed("ttl expired") |

All five are unit-testable in isolation today (per-component); integration
tests against a live server are the next iteration.
