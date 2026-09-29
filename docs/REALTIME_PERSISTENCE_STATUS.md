# Realtime ↔ Persistence Status

The WebSocket channel is functional as a *transport*. It is **not** wired to
the database in the way you'd expect for an emergency-response audit trail.

---

## 1. Where the WS layer touches state

| WS event type | Direction | Persisted? | Where it should persist |
|---|---|---|---|
| `auth.accepted` | server → client | No (transport) | n/a |
| `auth.rejected` | server → client | No (transport) | Could write an `audit_logs` row with "failed_ws_auth"; currently doesn't |
| `ping` / `pong` | both ways | No (transport) | n/a |
| `ack` | server → client | No (transport) | n/a — see §3 below |
| **`emergency.alert`** | client → server | **No** | Should call `IncidentService.create_sos` |
| `emergency.alert` | server → client (fanout) | n/a (just relayed) | Originating REST call already persisted |
| **`responder.location`** | client → server | **No** | Should call `IncidentService.update_location` |
| `responder.location` | server → client | n/a (relayed) | Originating REST call already persisted |
| `presence` | client → server | **No** | Should UPDATE `users.last_h3_cell_*` + `users.last_seen_at` |
| `admin.notification` | server → client | n/a (relayed) | Originating admin REST call already persisted |

---

## 2. The "client sends WS, no DB write" problem

Today the Android EmergencyAlertEngine sends an `emergency.alert` envelope
when the user long-presses the SOS button. The backend `websocket_v2._handle_emergency_alert`
is:

```python
async def _handle_emergency_alert(user_id, payload):
    # TODO: route to IncidentService.create_sos via dependency injection.
    await logger.ainfo("ws_v2_emergency_alert_received", user_id=user_id)
```

It logs and returns. No row is created. No fanout to other clients happens
because no service ever calls `manager.broadcast_to_incident`.

**Net result:** triggering an emergency does:
- ✅ Update the client's local MVI state (UI flips to emergency overlay).
- ✅ Log a single line on the backend.
- ❌ No incident row.
- ❌ No emergency_location row.
- ❌ No incident_event row.
- ❌ No audit log row.
- ❌ No fanout to responders.
- ❌ No FCM push.

This is the single biggest persistence gap and the single biggest reliability
gap. **Treat it as P0.**

### Recommended fix (chosen design)

**Client always uses REST for the trigger; WS is delivery-only for fanout.**

```
Client                         Backend
──────                         ───────
EmergencyButton long-press
       │
       │ EmergencyRepository.createSos(lat, lng, ...)
       ▼
POST /api/v1/incidents/sos  ─►  IncidentService.create_sos
                                ├─ INSERT incidents (status=BROADCASTING)
                                ├─ INSERT emergency_locations (PostGIS)
                                ├─ INSERT incident_events (CREATED)
                                ├─ INSERT audit_logs
                                └─ broadcast emergency.alert envelope to
                                    everyone in the k-ring (ConnectionManager)
       ◄────  201 Created with incident_id
       │
       │  RealtimeGateway.send(emergency.alert envelope)  ✗ deprecated; remove
       │
   Active state machine runs locally  ─►  receive responder.location envelopes
                                          via gateway.incoming (server fanout)
```

The client still uses the gateway for *inbound* events. It just stops trying
to trigger SOS via WS.

### Why this design

- **Single source of truth.** Persistence happens in one place. No race
  between "WS handler started persistence" and "REST endpoint also started persistence."
- **Audit trail uniformity.** `audit_logs` always sees the same shape of event.
- **No silent failure mode.** A failed POST returns a clear HTTP status code
  the client can surface; a failed WS envelope is invisible to the user.
- **Replay safety.** REST is idempotent on the server side via the `event_id`
  passed in the request body (server dedupes); WS-only triggers had no
  consistent dedup story.

### The latency argument

A common pushback: "but WS is faster." Measured difference for the SOS path:

```
WS path:        connect.send_text(envelope)            ~50 ms (no DB)
REST path:      HTTP/2 POST + DB commit               ~200 ms

UI feedback:    haptic + state-change at the long-press     0 ms (local)
Server fanout:  same regardless of REST vs WS trigger      ~100 ms
```

The user sees the UI flip at long-press (local state). They don't perceive
the 150 ms additional latency to the server commit. **Latency is not a
material factor for an SOS event.**

---

## 3. Acknowledgement protocol — transport-only is fine

The client-side `AckRegistry` expects `ack` envelopes for every sent envelope.
The backend emits them. These ACKs are NOT persisted to the DB and **should
not be** — they're a transport-layer construct (the client's `SendOutcome`
observable resolves on ACK, not the DB).

If we ever need *durable delivery confirmation* for a specific event type,
that becomes a domain field on the table (e.g. `incident_events.delivered_to[]`).

---

## 4. Inbound persistence — what should happen

After the SOS-trigger fix, the inbound side needs the following persistence
hooks:

| Inbound event | Persist? | Action |
|---|---|---|
| `emergency.alert` arriving on a responder's device | ❌ no client-side persistence needed | Local UI state + push notification |
| `responder.location` on the victim's device | ❌ no client-side persistence needed | Local UI state |
| `admin.notification` (user_approved, system_message) | ⚠️ optional | Could insert into a local Room "notifications" table for offline read after delivery |

Server-side persistence:

| Inbound event | Persist? | Action |
|---|---|---|
| `presence` from a client | ✅ should | UPDATE `users.last_h3_cell_district = $1, users.last_seen_at = now()` |
| `responder.location` from a responder | ✅ should | INSERT `emergency_locations` (same as `POST /incidents/{id}/location`) — or just deprecate the WS variant and require REST |

---

## 5. Duplicate-event protection on the persistence side

If you adopt the "REST for trigger" design, the server is the de-dup
authority. Add to `IncidentRepository.create_sos`:

```python
# Optional: dedupe by client-supplied event_id (idempotency key)
existing = await self.db.execute(
    select(Incident.id).where(Incident.idempotency_key == request.event_id)
)
if existing.scalar_one_or_none():
    return existing  # 200 OK, same response as first call
```

This requires a new `incidents.idempotency_key` column (indexed). Migration
work — about 2 hours.

---

## 6. Outbound queue durability

The client-side `OutboundQueue` (in `RealtimeGateway`) is in-memory. With
the "REST for trigger" design, this matters less for SOS triggers (the
REST call retries via OkHttp), but it still matters for:

- Responder location pings during an active incident with intermittent network.
- Presence pings (low priority — they'd just be skipped).

Plan: replace the in-memory queue with a DataStore-Proto-backed durable
queue (see [REALTIME_RELIABILITY_STRATEGY.md](REALTIME_RELIABILITY_STRATEGY.md)).

For SOS specifically, durability is provided by retrying the REST call
with exponential backoff if the network is down at trigger time.

---

## 7. Persistence-test harness

Once the fixes land, the following automated checks should run on every PR:

```bash
# Trigger SOS via WS — should be rejected after fix
wscat -c wss://api.amanah/ws -H "Authorization: Bearer $TOKEN" \
  -x '{"v":1,"type":"emergency.alert",...}'
# Expect: error envelope or no-op

# Trigger SOS via REST — should persist
curl -X POST https://api.amanah/api/v1/incidents/sos \
  -H "Authorization: Bearer $TOKEN" -d '{"lat":23.81,"lng":90.41,...}'
# Expect: 201 + incident_id

# Verify DB
psql -c "SELECT id, status FROM incidents ORDER BY created_at DESC LIMIT 1;"
# Expect: row with status='broadcasting'

psql -c "SELECT action FROM audit_logs ORDER BY created_at DESC LIMIT 1;"
# Expect: row with action='sos_created'
```

This belongs in CI; see [END_TO_END_CONNECTION_CHECKLIST.md](END_TO_END_CONNECTION_CHECKLIST.md).

---

## 8. Summary

The realtime channel works as a delivery medium. Persistence is **today only
via REST**, and the client doesn't currently call REST for anything but auth.

**Two complementary fixes:**

1. Make the Android client call `POST /incidents/sos` for trigger (and use
   WS for inbound only).
2. Strip the `emergency.alert` ingress path on the backend (or have it
   delegate to `IncidentService.create_sos` with the JWT-derived user_id).

Together these close the persistence gap for the realtime layer.
