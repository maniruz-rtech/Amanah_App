# FCM Wakeup Architecture

WebSocket alone isn't enough for emergency delivery. Android can — and
will — kill the app process under memory pressure, severing the WS
connection. FCM is the standby channel that wakes the process back up
when there's something important to deliver.

## End-to-end flow

```
Backend: IncidentService.create_sos  (or any urgent event)
     │
     ▼
services/push.py  → FCM SDK → Google FCM endpoint
     │
     ▼  (silent data push, priority=high)
Android system    delivers to AmanahFirebaseMessagingService.onMessageReceived
     │
     ▼
PushBus.onWakeup() / onIncomingAlert() / onTokenRefreshed()
     │
     ▼
AppGraph.startPushIntegration() subscribers:
   - wakeups → realtimeGateway.connect()
   - tokens  → deviceRepository.register(deviceUuid, fcmToken)
   - alerts  → (UI surface — wired by interactor when dashboard is active)
     │
     ▼
Gateway re-opens WSS → server delivers buffered events normally
```

## Three message classes

| Class | Trigger | Payload | Notification? |
|---|---|---|---|
| **wakeup** | Server detects WS is offline but has events pending | `{ "kind": "wakeup" }` | No (silent) |
| **emergency.alert** | New SOS broadcast for an offline nearby user | `{ "kind": "emergency.alert", "alert_id": ..., "title": ..., "body": ..., "lat": ..., "lng": ... }` | Yes — high-priority |
| **admin.notification** | Account approval, suspension, system message | `{ "kind": "admin.notification", "type": "user_approved", "message": ... }` | Yes — default channel |

## Android implementation

[feature-core/push/AmanahFirebaseMessagingService.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/push/AmanahFirebaseMessagingService.kt):

- Single FCM service registered in the manifest.
- Dispatches by `data.kind`.
- Token refreshes go through [PushBus](../feature-core/src/main/kotlin/com/amanah/feature/core/push/PushBus.kt) → graph.
- Emergency notifications use `IMPORTANCE_HIGH` + `CATEGORY_ALARM` so
  they bypass DND on Android 14+ (when the user grants the alarms-only
  permission).

The bus is a static singleton because Android instantiates the
`FirebaseMessagingService` itself — we can't inject anything into it.
The bus is the only stable bridge.

## Backend implementation

[backend/app/services/push.py](../backend/app/services/push.py):

```python
def send_wakeup(device_tokens: Iterable[str]) -> None: ...
def send_emergency_alert(device_tokens, *, alert_id, title, body, lat, lng, extra) -> None: ...
```

Both functions are:

- **No-ops** when `FCM_ENABLED=false` (so dev environments don't need
  Firebase creds).
- **Import-safe** even if `firebase-admin` isn't installed (graceful
  ImportError handling at first-use).
- **Best-effort** — failures log a warning but never block the parent
  request. An SOS that succeeds the DB write still returns 201 even if
  the push fails; the WS path will still deliver to online clients.

## Wiring into IncidentService

```python
# backend/app/services/incident.py — sketch for production
async def _broadcast_to_responders(self, incident: Incident) -> None:
    responders = await self.responder_repo.find_nearby_active(...)
    # ① WS broadcast (already wired)
    await manager.broadcast_emergency_alert(incident.id, responders)
    # ② Push fanout for off-WS users
    tokens = [r.devices[0].push_token for r in responders if r.devices and r.devices[0].push_token]
    push.send_emergency_alert(
        device_tokens = tokens,
        alert_id      = incident.id,
        title         = "Nearby emergency",
        body          = f"A member needs help within {radius_km}km",
        lat           = lat, lng = lng,
    )
```

In the current cut, `_broadcast_to_responders` does the WS step but
the FCM step is left as a Celery task hook. Wiring the Celery task is
tracked as P0 #3 in the production-readiness plan.

## Token registration

```
First launch after sign-in:
  FirebaseMessaging.getInstance().token.addOnSuccessListener { token ->
      PushBus.onTokenRefreshed(token)
  }
  → graph subscribes →
  → DeviceRepository.register(deviceUuid, fcmToken)
  → backend persists in `devices.push_token`
```

The device UUID is read once from
`Settings.Secure.ANDROID_ID`, stored alongside the token. The same UUID
is sent on each login so the backend can rotate the token on subsequent
sessions.

## Notification permission (Android 13+)

`POST_NOTIFICATIONS` is now a runtime permission. The onboarding flow
requests it after the location permission. If denied, the FCM service
still runs and silent wakeups still work — only the visible
notifications would be hidden.

## Notification channel

Created lazily in `AmanahFirebaseMessagingService.postEmergencyNotification`:

| Channel | ID | Importance | Use |
|---|---|---|---|
| Emergency alerts | `amanah_emergency` | `IMPORTANCE_HIGH` | Visible emergency pushes |
| Active emergency | `amanah_emergency_fg` | `IMPORTANCE_HIGH` | Persistent foreground service notification |
| (future) Admin | `amanah_admin` | `IMPORTANCE_DEFAULT` | Approvals, suspensions, etc. |

## Resilience scenarios

| Scenario | Outcome |
|---|---|
| App is killed, FCM wakeup arrives | Service is started, gateway reconnects, gateway pulls buffered events |
| FCM is down | WS-only path still delivers to online clients; once Firebase recovers, queued pushes deliver in order |
| Token rotates mid-session | `onNewToken` fires → bus pushes → DeviceRepository.register updates server |
| User denies notification permission | Silent wakeup still works (data-only payload doesn't require POST_NOTIFICATIONS); only the visible UI is hidden |
| User uninstalls + reinstalls | New token issued; `Settings.Secure.ANDROID_ID` may also rotate on Android 8+ for the new install — backend treats this as a new device row |
