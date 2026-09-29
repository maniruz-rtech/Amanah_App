# Foreground Service Design

## Rationale

Without a foreground service, Android can — and on memory-constrained
devices, **will** — kill the app process under memory pressure. For a
chat app or a feed reader this is fine. For an emergency-response app
this is a safety failure: the WebSocket dies, location updates stop, and
the user only learns about it when they realise their SOS never
broadcast.

A foreground service trades a persistent notification for these
guarantees:

- The process is **not killed** under normal memory pressure.
- Background-execution restrictions (Doze, App Standby) do not apply.
- The notification is **visible to the user** — they always know an
  emergency is in progress.

## Implementation

[feature-core/emergency/EmergencyForegroundService.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/emergency/EmergencyForegroundService.kt):

```kotlin
class EmergencyForegroundService : Service() {
    companion object {
        fun start(ctx: Context, alertId: String) { ... }
        fun stop(ctx: Context) { ... }
    }
}
```

Manifest declaration (see [app/src/main/AndroidManifest.xml](../app/src/main/AndroidManifest.xml)):

```xml
<service
    android:name="com.amanah.feature.core.emergency.EmergencyForegroundService"
    android:foregroundServiceType="location|specialUse"
    android:exported="false">
    <property
        android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"
        android:value="amanah:active-emergency-tracking" />
</service>
```

Two `foregroundServiceType` flags:

- `location` — we keep collecting location during the emergency. This
  is the right semantic flag and satisfies Android 14's foreground-type
  enforcement.
- `specialUse` — required as a catch-all for the broader process-anchor
  purpose (gateway survival). The `PROPERTY_SPECIAL_USE_FGS_SUBTYPE`
  property documents what we're doing for the Play Store reviewer.

## Lifecycle

```
EmergencyFeature FSM transitions to any active phase
  → UserDashboardInteractor.subscribe sees isActiveEmergency
    → locationProvider.start(EMERGENCY)
    → EmergencyForegroundService.start(appContext, alertId)

User cancels or admin resolves
  → engine FSM returns to IDLE
    → locationProvider.start(ACTIVE)        // demote
    → EmergencyForegroundService.stop(ctx)

User force-stops the app
  → service is killed by the system
  → next launch: EmergencyAlertEngine re-fetches active incidents via
    /incidents/my/active and restarts the foreground service if any
```

## Notification

A single persistent notification on channel `amanah_emergency_fg`:

- **Title:** "Emergency in progress"
- **Body:** "Amanah is tracking the incident in the background"
- **Ongoing:** `true` — cannot be dismissed by swipe
- **OnlyAlertOnce:** `true` — no sound/vibrate spam if we re-attach
- **Priority:** `PRIORITY_HIGH` so it shows in the heads-up area on
  Android 14+ when the screen is locked
- **ContentIntent:** opens MainActivity, which routes to the
  active-emergency overlay

## Battery optimisation

Android may put the app in App Standby Buckets if the user doesn't open
the app frequently. The foreground service exempts the app from these
buckets *while the service is running*, which is exactly when we need
it. Once the emergency clears and the service stops, the app returns to
normal Standby behaviour.

For users who have enabled "Restrict background activity" or
"Battery optimisation" in system settings, the service still works (the
foreground notification is the contract) but reconnects may be slower
during cold-start. We surface a one-time prompt during onboarding to
disable battery optimisation for Amanah specifically; the user can skip
it.

## Process death recovery

The service is `START_STICKY`. If the system kills it under extreme
memory pressure, Android restarts the service with a `null` intent.
On restart we read the current emergency state from
`EmergencyAlertEngine.cachedState` (or, if the engine is also dead, the
`/incidents/my/active` REST endpoint) and update the notification
accordingly.

## Android version matrix

| API level | Behaviour |
|---|---|
| 26 (O) | `startForegroundService` + `startForeground` within 5s |
| 29 (Q) | `foregroundServiceType` declaration required for location use |
| 31 (S) | Background-start restrictions tightened; we always start from a foreground context (`MainActivity` / `UserDashboardInteractor`) |
| 34 (U) | `specialUse` flag + `PROPERTY_SPECIAL_USE_FGS_SUBTYPE` required for non-standard foreground services |

## Testing matrix

| Scenario | Expected |
|---|---|
| Long-press SOS → backend reaches the broadcast phase | Service starts; notification appears |
| User puts phone screen off | WS stays alive; location updates continue at EMERGENCY cadence |
| User unlocks → resolve → app foregrounds | Service stops; notification dismisses |
| User force-stops app mid-emergency | Service stops; foreground notification dismisses; on next launch the engine re-fetches incident state and restarts the service if alert is still active |
| Low-memory device kills the service | `START_STICKY` causes restart; notification reappears with the most recent alertId |

## Trade-offs

- The persistent notification is intentional. There is no "stealthy"
  emergency mode — the user must see that tracking is active.
- We do not run the service when there is no active emergency. The
  WebSocket reconnects via the normal `OkHttpRealtimeGateway` lifecycle
  when the app is in the foreground; FCM wakeup handles the killed-app
  case.
- We do not request `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` automatically
  — that's a hostile UX and Play Store now scrutinises it. We offer a
  manual "Optimise Amanah for emergency response" link in Settings that
  opens the system battery-optimisation page.
