# SOS Persistence Flow

> **The rule:** every emergency trigger MUST leave a forensic trace before
> the user sees confirmation. REST is the single source of truth; the
> WebSocket is delivery-only.

## End-to-end chain

```
┌────────────────────────────────────────────────────────────────────────┐
│  Android (com.amanah.app)                                              │
│                                                                        │
│  ① User long-presses EmergencyButton (UserDashboardView)               │
│                       │                                                │
│                       ▼                                                │
│  ② UserFeature.accept(UserWish.TriggerEmergency)                       │
│                       │ → effect EmergencyTriggered → news Triggered   │
│                       ▼                                                │
│  ③ EmergencyFeature.accept(EmergencyWish.TriggerAlert(lat, lng, uid))  │
│                       │ → effect BroadcastStarted → news Broadcast     │
│                       ▼                                                │
│  ④ EmergencyAlertEngine.persistAlertViaRest(news)                      │
│                       │                                                │
│                       ▼                                                │
│  ⑤ EmergencyRepository.createSos(lat, lng, h3Cell, ...)                │
│        │             retries on NetworkDown / 5xx (4 attempts)         │
│        │             AuthFailed short-circuits to login                │
│        ▼                                                                │
│  ⑥ ApiService.createSos(SosRequest)                                    │
│        │   AuthInterceptor: Authorization: Bearer <jwt>                │
│        │   RefreshInterceptor: single-flight refresh on 401            │
│        ▼                                                                │
│  ⑦ HTTPS (pinned: PinningConfig.PRIMARY_PIN + BACKUP_PIN)              │
│                       │                                                │
│                       ▼                                                │
└─────────────────────────────│──────────────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────────────────┐
│  Backend (FastAPI)                                                     │
│                                                                        │
│  ⑧ POST /api/v1/incidents/sos                                          │
│        │  AuthenticatedUser dependency: JWT → user_id from sub claim   │
│        ▼                                                                │
│  ⑨ IncidentService.create_sos(user_id, organization_id, region_id,     │
│                                request)                                 │
│        │                                                                │
│        ▼                                                                │
│  ⑩ IncidentRepository.create_sos(...)                                  │
│        ┌──────────────────────────────────────────────────────────┐    │
│        │ ATOMIC TRANSACTION (single AsyncSession via get_db)      │    │
│        │                                                          │    │
│        │  INSERT incidents                                        │    │
│        │    (id ULID prefixed inc_, status=BROADCASTING,          │    │
│        │     incident_type, severity, organization_id, region_id) │    │
│        │                                                          │    │
│        │  INSERT emergency_locations                              │    │
│        │    (id ULID prefixed loc_, lat, lng,                     │    │
│        │     location = ST_SetSRID(ST_MakePoint(lng,lat), 4326),  │    │
│        │     captured_at = NOW(), expires_at = +90 days)          │    │
│        │                                                          │    │
│        │  INSERT incident_events                                  │    │
│        │    (id ULID prefixed evt_, event_type=CREATED,           │    │
│        │     actor_user_id=user_id, payload={lat,lng,silent_mode})│    │
│        │                                                          │    │
│        │  INSERT audit_logs                                       │    │
│        │    (id ULID prefixed aud_, action='sos_created',         │    │
│        │     resource_type='incident', resource_id=incident.id)   │    │
│        │                                                          │    │
│        └──────────────────────────────────────────────────────────┘    │
│        │     get_db's auto-commit closes the transaction              │
│        ▼                                                                │
│  ⑪ IncidentService broadcasts emergency.alert WS envelope to nearby    │
│     users (via ConnectionManager).                                     │
│        │                                                                │
│        ▼                                                                │
│  ⑫ Response: HTTP 201 + SOSCreateResponse(incident_id, status, ts)     │
└─────────────────────────────│──────────────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────────────────┐
│  Android (back in EmergencyAlertEngine)                                │
│                                                                        │
│  ⑬ Outcome.Success → engine.feature.accept(EmergencyWish.AlertConfirmed│
│                       (alertId=server.id, h3Cell, lat, lng))           │
│  ⑭ Engine confirms its FSM, which propagates to UserFeature via the    │
│     emergencyFeature.states subscription.                              │
│  ⑮ UI flips to active-emergency overlay with the SERVER-assigned       │
│     incident_id.                                                       │
└────────────────────────────────────────────────────────────────────────┘
```

## Forensic guarantee

Every successful SOS leaves **exactly four rows in four tables, all in
one atomic transaction**:

| Table | Row purpose |
|---|---|
| `incidents` | The incident itself (status=BROADCASTING) |
| `emergency_locations` | PostGIS geography point + lat/lng + accuracy |
| `incident_events` | Audit trail entry: `event_type=created` |
| `audit_logs` | System-wide audit: `action=sos_created` |

If any of these fails, the entire transaction rolls back. There is no
half-persisted state.

This is verified by `scripts/smoke_e2e.sh` step 6:

```
✔ deltas: incidents +1, locations +1, events +1, audit +1
```

## What does NOT persist (intentional)

- **The WebSocket envelope** that the server broadcasts to other clients
  isn't a separate persisted row — it's a consequence of the
  already-committed incident. If a fanout listener drops the envelope, the
  delivery system (FCM, reconnect-replay) recovers because the source of
  truth is the DB row.
- **The client's local MVI state** is ephemeral. Process death restores
  state by reading `GET /incidents/my/active` on next launch.

## Why REST, not WebSocket, for the trigger

Earlier design considered "send WS `emergency.alert` envelope first, persist
asynchronously." That was rejected because:

1. **Single source of truth.** Persistence in one place. No race between
   "WS handler started persistence" and "REST endpoint also started
   persistence."
2. **Audit-trail uniformity.** Every action that produces an `audit_logs`
   row goes through the same service layer.
3. **Failure visibility.** A REST 5xx is a clear actionable signal to the
   client; a dropped WS envelope is silent.
4. **Idempotency.** The server can dedupe by `event_id` on POST (planned
   improvement); the WS path had no consistent dedup story.
5. **Latency is not material.** The added 150 ms vs. WS is invisible to the
   user — local UI state flips at long-press regardless.

## Retry strategy

`EmergencyRepository.createSos` retries up to **4 attempts** with full-
jitter backoff: 500 ms → 1 s → 2 s → 4 s. Terminal outcomes
(`AuthFailed`, `ServerError 4xx other than 401/403`, `Unexpected`) do not
retry. If all retries exhaust, the engine emits
`EmergencyWish.AlertError(message)` which the UI surfaces as a hard error.

The user is therefore guaranteed to receive an explicit positive
confirmation OR an explicit failure — never silent loss.

## Cancellation path

Symmetric to trigger:

```
EmergencyButton "Cancel Emergency"
  → UserFeature.CancelEmergency
  → EmergencyFeature.CancelAlert → news AlertCancelled
  → EmergencyAlertEngine.cancelViaRest
  → EmergencyRepository.cancel(incidentId, reason)
  → POST /api/v1/incidents/{id}/cancel
  → backend updates incidents.status, writes incident_events
```

Note: the backend requires a 4-digit `verification_pin` for cancel today
(legacy spec — admin-issued). That's a separate hardening item; the demo
path uses force-cancel via the admin user.

## Validation

Run the smoke test against the live stack:

```bash
$ ./scripts/smoke_e2e.sh

✔ API healthy: ...
✔ logged in as usr_01KS5ZCBVVJYQMJ5N3AVMCVQQ6
✔ /users/me returns matching user
✔ Baseline DB counts
✔ incident created: inc_01KS5ZKGSAR3Z1XB0C44EASWPW
✔ deltas: incidents +1, locations +1, events +1, audit +1
✔ ST_AsText(location) = POINT(90.4125 23.8103)
✔ incident status: broadcasting

✔ PASS — end-to-end persistence chain verified.
```
