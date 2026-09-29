# Incident Coordination Flow

## Lifecycle state machine

The backend enforces a strict per-incident state machine. Defined in
[backend/app/db/enums.py](../backend/app/db/enums.py)
`VALID_INCIDENT_TRANSITIONS`:

```
                ┌──────────┐
                │  DRAFT   │
                └────┬─────┘
                     │ → ACTIVE
                ┌────▼─────┐
                │  ACTIVE  │
                └────┬─────┘
                     │ → BROADCASTING
                ┌────▼─────────┐
                │ BROADCASTING │  ← created here by POST /incidents/sos
                └────┬─────────┘
       ┌─────────────┼─────────────┐
       │ → ACCEPTED  │ → CANCELED  │ → EXPIRED
       ▼             ▼             ▼
   ┌────────┐    ┌──────────┐   ┌─────────┐
   │ACCEPTED│    │CANCELED  │   │EXPIRED  │  (terminal)
   └───┬────┘    └──────────┘   └─────────┘
       │ → EN_ROUTE
       ▼
   ┌────────┐
   │EN_ROUTE│
   └───┬────┘
       │ → ARRIVED
       ▼
   ┌────────┐
   │ARRIVED │
   └───┬────┘
       │ → RESOLVED
       ▼
   ┌────────┐
   │RESOLVED│ (terminal)
   └────────┘
```

Any other transition raises `InvalidStateTransitionError` →
HTTP 400 to the API caller.

Every transition writes an `incident_events` row (audit) and an
`audit_logs` row (system-wide).

## Responder side — the four primary actions

| Action | Endpoint | Effect |
|---|---|---|
| Accept assignment | `POST /api/v1/responders/incidents/{id}/accept` | `assignment.status = ACCEPTED`; incident moves to ACCEPTED |
| Decline | `POST /api/v1/responders/incidents/{id}/decline` | `assignment.status = DECLINED`; incident may stay BROADCASTING for next responder |
| En route | `POST /api/v1/responders/incidents/{id}/en-route` | Incident → EN_ROUTE; location pings begin |
| Arrived | `POST /api/v1/responders/incidents/{id}/arrived` | Incident → ARRIVED |

Server-side conflict prevention:

- The first responder to accept "wins" assignment of the incident; any
  later acceptance is silently rejected with HTTP 409.
- A responder can only en-route → arrived → resolved on incidents they
  have an ACCEPTED assignment to. Enforced server-side via
  `IncidentAssignment.responder_id == current_user_id`.

## Android-side wiring

[feature-emergency/repository/ResponderRepository.kt](../feature-emergency/src/main/kotlin/com/amanah/feature/emergency/repository/ResponderRepository.kt) is the canonical surface:

```kotlin
suspend fun getAvailability(): Outcome<AvailabilityDto>
suspend fun setAvailability(...): Outcome<AvailabilityDto>
suspend fun accept(incidentId: String, etaMinutes: Int): Outcome<IncidentDto>
suspend fun decline(incidentId: String, reason: String): Outcome<IncidentDto>
suspend fun enRoute(incidentId: String, lat: Double, lng: Double, etaSeconds: Int? = null): Outcome<IncidentDto>
suspend fun arrived(incidentId: String): Outcome<IncidentDto>
```

Use case sketch:

```kotlin
// User on responder side receives an emergency.alert via gateway.incoming
// → UI surfaces an "Incoming alert: Accept / Decline" dialog
// → onAccept:
viewModelScope.launch {
    when (val outcome = responderRepository.accept(incidentId, etaMinutes = 8)) {
        is Outcome.Success -> {
            // Begin en-route flow
            locationProvider.start(TrackingProfile.EMERGENCY)
            EmergencyForegroundService.start(ctx, incidentId)
            startEnRouteLocationLoop(incidentId)
        }
        Outcome.AuthFailed -> kickToLogin()
        else -> showError()
    }
}
```

## Realtime updates

When any responder transition fires server-side, the backend broadcasts
an `emergency.alert` WS envelope with the new status to:

- The **victim**'s WS client → `UserDashboardInteractor` sees the
  status field change and updates the responder list / ETA card.
- Other **nearby responders**' clients → they see the responder count
  ticking up.
- **Admin** clients → AdminAlertDetail screen updates in real time.

Wire format (unchanged across the lifecycle):

```json
{ "v":1, "type":"emergency.alert", "event_id":"…", "ts":…,
  "payload": {
    "alert_id": "inc_…",
    "victim_id": "usr_…",
    "lat": ..., "lng": ...,
    "h3_cell": "…",
    "status": "ACCEPTED" | "EN_ROUTE" | "ARRIVED" | "RESOLVED" | "CANCELED",
    "k_ring": 1
  }
}
```

The client's `EmergencyAlertEngine.onIncomingAlert` switches on the
`status` field:

- `ACTIVE` (initial) — gate via ProximityMatcher; if in range, confirm
- `RESOLVED` / `CANCELED` / `TIMED_OUT` — fire `EmergencyWish.ResolveAlert`

For intermediate statuses (`ACCEPTED`, `EN_ROUTE`, `ARRIVED`), the
engine updates its phase, which the UI projects onto the active-emergency
overlay (e.g. "Responder accepted • ETA 8 min" → "Responder en route" →
"Responder arrived").

## Audit trail

For every coordination action the backend writes:

- An `incident_events` row with `event_type = RESPONDER_ACCEPTED |
  RESPONDER_DECLINED | RESPONDER_EN_ROUTE | RESPONDER_ARRIVED |
  RESPONDER_COMPLETED`.
- An `audit_logs` row with the matching action.

Forensic reconstruction of any incident is therefore:

```sql
SELECT event_type, actor_user_id, event_payload, created_at
FROM incident_events
WHERE incident_id = $1
ORDER BY created_at ASC;
```

Which yields a complete causal timeline.

## Edge cases

| Case | Server behaviour |
|---|---|
| Two responders accept simultaneously | First wins; second gets HTTP 409 |
| Responder declines after accepting | Allowed; incident drops back to BROADCASTING; ACCEPTED responder slot frees |
| Responder en-route → user cancels | Incident → CANCELED; responder gets `emergency.alert` with `status=CANCELED`; foreground service stops |
| Responder arrives but never marks → user resolves | User cannot directly resolve; admin force-resolve is the path |
| Admin force-resolve mid-en-route | Allowed; all responder assignments closed; everyone gets the WS event |
| Responder loses connectivity mid-en-route | WS reconnects; status is re-fetched via `/incidents/{id}` on resume |

## UI state mapping

The Android client maps backend status → Android `EmergencyState.Phase`:

| Backend | Android |
|---|---|
| `BROADCASTING` | `BROADCASTING` |
| `ACCEPTED` | `CALCULATING_ETA` (until first responder.location update) |
| `EN_ROUTE` | `RESPONDER_EN_ROUTE` |
| `ARRIVED` | `RESPONDER_EN_ROUTE` (visual stays — server resolves shortly) |
| `RESOLVED` / `CANCELED` | `IDLE` (UI closes overlay) |

## Future work

- **Multi-responder acceptance.** The current contract is "first
  accept wins." Future: allow N responders to accept and surface all
  ETAs to the victim.
- **Server-side dispatch heuristic.** Today every nearby responder
  receives the WS broadcast. A future iteration will pick the top-3
  by distance + availability + battery and broadcast only to them
  first, escalating to the wider k-ring after 30 s if none accept.
- **Escalation timer.** If `BROADCASTING` for more than 90 s with no
  accept, server expands the k-ring or pages admins.
