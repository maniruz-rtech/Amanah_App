# Location System Architecture

The location subsystem is built around three pillars: **a clean interface
contract**, **a battery-aware tracking profile**, and **a privacy-aware
output shape**.

## Interface

[feature-core/location/LocationProvider.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/location/LocationProvider.kt)

```kotlin
interface LocationProvider {
    val stream: Observable<LocationFix>
    fun snapshot(): LocationFix?
    fun start(profile: TrackingProfile)
    fun stop()
    fun currentH3Cell(resolution: H3Resolution = H3Resolution.DISTRICT): String?
}
```

Why three access shapes:

- `snapshot()` — the SOS button path. We cannot wait for a fresh fix; we
  use the last-known one. Returns null if none yet, in which case the
  trigger lets the server-side ST_MakePoint(0,0) sentinel through and the
  validator returns a clear error.
- `stream`  — reactive subscribers (the engine + the dashboard nearby
  loader). Hot stream; subscribers see every fix from now on.
- `currentH3Cell(resolution)` — cached H3 lookup. Avoids re-deriving from
  lat/lng for every nearby presence ping.

## Tracking profiles

| Profile | Cadence | Min displacement | Priority |
|---|---|---|---|
| `IDLE` | 60 s | 50 m | Balanced |
| `ACTIVE` | 10 s | 10 m | High |
| `EMERGENCY` | 1 s | 0 m | High |

The interactor picks the profile:

- **dashboard attaches → `ACTIVE`** (the user is interacting; cheap GPS is fine)
- **emergency goes live → `EMERGENCY`** (full firehose)
- **emergency clears → back to `ACTIVE`**
- **dashboard detaches → `stop()`**

The profile is enforced by the `FusedLocationProviderClient` via
`LocationRequest.setMinUpdateDistanceMeters(...)` so battery isn't drained
when the user is stationary.

## Implementation

[feature-core/location/FusedLocationProvider.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/location/FusedLocationProvider.kt)

- Uses `LocationServices.getFusedLocationProviderClient(context)`.
- Permission-aware: if neither `ACCESS_FINE_LOCATION` nor `ACCESS_COARSE_LOCATION`
  is granted, `start()` is a no-op (logs a warning). The UI prompts the
  user via the standard runtime-permission flow on first launch.
- Battery level is read via `BatteryManager.BATTERY_PROPERTY_CAPACITY` and
  surfaced on every `LocationFix`. The backend reads this when computing
  responder fatigue.
- Thread-safety: `lastFix` is an `AtomicReference`; subscribers see updates
  on the main looper (Fused's default).

## Privacy boundary

The provider returns raw GPS in `LocationFix.{lat, lng}`. The downstream
**privacy contract** says:

- Presence pings to `/users/me/presence` carry only the **H3 cells**, not
  raw GPS.
- `/users/nearby` returns only the matched users' H3 cells, never their
  raw GPS.
- Raw GPS leaves the device only inside the SOS body (which the user
  explicitly triggered) and in the responder's `/responders/incidents/{id}/en-route`
  body (an opt-in coordination signal during an active alert).

Implementation:

```kotlin
// Presence ping path — H3 cells only, never raw GPS
locationProvider?.currentH3Cell()?.let { h3 ->
    userRepository.pingPresence(h3, locationProvider?.currentH3Cell(H3Resolution.BLOCK))
}
```

```kotlin
// SOS path — raw GPS goes through, since the user explicitly triggered
emergencyRepository.createSos(lat = fix.lat, lng = fix.lng, h3Cell = fix.h3)
```

## Lifecycle integration

```
RootNode.showUserDashboard
  → UserDashboardNode created with locationProvider
  → UserDashboardInteractor.initializeUser
    → locationProvider.start(ACTIVE)
    → loadInitialFromBackend
      → repository.pingPresence(h3) every 60s (scheduled in next iteration)
      → repository.listNearby(kRingCells)

  → EmergencyAlertEngine detects isActiveEmergency
    → locationProvider.start(EMERGENCY)
    → EmergencyForegroundService.start(ctx, alertId)

  → engine FSM returns to IDLE
    → locationProvider.start(ACTIVE)
    → EmergencyForegroundService.stop(ctx)

  → UserDashboardInteractor.onDetach
    → locationProvider.stop()
```

## Permission flow

The Android manifest declares (see [app/src/main/AndroidManifest.xml](../app/src/main/AndroidManifest.xml)):

```xml
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_LOCATION" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
```

The runtime prompt flow (deferred to the onboarding screen — see
[FOREGROUND_SERVICE_DESIGN.md](FOREGROUND_SERVICE_DESIGN.md)):

1. **Onboarding step 2** explains why we need location.
2. **System dialog** requests `ACCESS_FINE_LOCATION`.
3. **If denied** → app still works, but `currentH3Cell()` returns null and
   the nearby grid is empty. The user sees an "Enable location to see
   nearby members" banner.
4. **Background location** is NOT requested at install time; the
   foreground service is the appropriate channel and avoids the
   problematic Android 11+ "Allow all the time" UX.

## Testing

- `FusedLocationProvider.start(IDLE)` with permission revoked → no
  callback registered (verified by logcat warning).
- `FusedLocationProvider.start(EMERGENCY)` → 1-Hz callbacks observed.
- `currentH3Cell(BLOCK)` consistently returns resolution-9 cells for a
  given fix.
- Battery level read returns 0..100 or null on emulators where the
  BatteryManager service is absent.
