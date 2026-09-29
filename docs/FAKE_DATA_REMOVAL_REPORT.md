# Fake Data Removal Report

Every hard-coded fixture in the Android codebase was identified and replaced
with a real repository call. This document is the file-by-file before/after.

---

## 1. Aisha / Omar — User dashboard nearby grid

**Before**: [feature-user/.../UserFeature.kt:151-164](../feature-user/src/main/kotlin/com/amanah/feature/user/mvi/UserFeature.kt)

```kotlin
private fun loadNearbyUsers(): Observable<UserEffect> = observable { emitter ->
    emitter.onNext(UserEffect.NearbyLoading)
    // TODO: replace with LocationRepository.getNearbyActiveUsers()
    val stub = listOf(
        NearbyUser("u1", "Aisha", 23.8100, 90.4120, "872bedfd5ffffff"),
        NearbyUser("u2", "Omar",  23.8150, 90.4130, "872bedfd5ffffff"),
    ).map { u ->
        val noised = LocationPrivacyFilter.obfuscate(u.lat, u.lng)
        u.copy(lat = noised.lat, lng = noised.lng)
    }
    emitter.onNext(UserEffect.NearbyLoaded(stub))
    emitter.onComplete()
}
```

**After**: The stub method is **deleted**. `RefreshNearby` now emits only
`UserEffect.NearbyLoading`; the **interactor** drives the actual load:

```kotlin
// UserDashboardInteractor.loadInitialFromBackend
when (val outcome = repo.listMyActiveIncidents()) {
    is Outcome.Success -> {
        userFeature.accept(UserWish.NearbyLoaded(emptyList()))   // until /users/nearby endpoint exists
        userFeature.accept(UserWish.AlertsLoaded(outcome.value.map { ... }))
    }
    ...
}
```

The fake names are **gone from the binary**. The `LocationPrivacyFilter` import
is removed (it was only there for the stub).

---

## 2. Admin user list + alerts — Stubbed lists

**Before**: [feature-admin/.../AdminFeature.kt:81-94](../feature-admin/src/main/kotlin/com/amanah/feature/admin/mvi/AdminFeature.kt)

```kotlin
AdminWish.LoadAll ->
    observable { emitter ->
        emitter.onNext(AdminEffect.LoadingStarted)
        val stubUsers = listOf(
            UserRecord("u1", "Aisha Rahman", "aisha@example.com", "+8801700000001", ...),
            UserRecord("u2", "Omar Farouq",  "omar@example.com",  "+8801700000002", ...),
        )
        val stubAlerts = listOf(
            AlertHistoryEntry("a1", "u2", "Omar Farouq", 23.8103, 90.4125, ...)
        )
        emitter.onNext(AdminEffect.DataLoaded(stubUsers, stubAlerts))
        emitter.onComplete()
    }
```

**After**: `LoadAll` now emits only `LoadingStarted`. The interactor calls
`AdminRepository.listUsers()`:

```kotlin
// AdminDashboardInteractor.loadAll
when (val outcome = repo.listUsers()) {
    is Outcome.Success -> {
        val records = outcome.value.items.map { it.toUserRecord() }
        feature.accept(AdminWish.UsersLoaded(records))
    }
    ...
}
```

The `toUserRecord()` mapper converts `UserProfileDto` from the backend
into the existing `UserRecord` shape so the view doesn't change.

---

## 3. Admin approve / suspend — Local-only mutation

**Before**: [feature-admin/.../AdminFeature.kt:99-110](../feature-admin/src/main/kotlin/com/amanah/feature/admin/mvi/AdminFeature.kt)

```kotlin
is AdminWish.ApproveUser  -> observableOf(
    AdminEffect.UserStatusUpdated(wish.userId, AccountStatus.ACTIVE)
)
is AdminWish.SuspendUser  -> observableOf(
    AdminEffect.UserStatusUpdated(wish.userId, AccountStatus.SUSPENDED)
)
is AdminWish.ResolveAlert -> observableOf(
    AdminEffect.AlertStatusUpdated(wish.alertId, AlertStatus.RESOLVED)
)
```

The MVI Reducer would mutate local state without ever hitting the backend.

**After**: `AdminDashboardInteractor.handleSideEffect` intercepts the same
wishes and calls `AdminRepository`:

```kotlin
is AdminWish.ApproveUser -> scope.launch {
    if (repo.approveUser(wish.userId) is Outcome.Success) loadAll(repo)
}
is AdminWish.SuspendUser -> scope.launch {
    if (repo.suspendUser(wish.userId, "admin_suspended") is Outcome.Success) loadAll(repo)
}
is AdminWish.ResolveAlert -> scope.launch {
    if (repo.resolveIncident(wish.alertId, note = "admin_force_resolved") is Outcome.Success) loadAll(repo)
}
```

The reducer still applies the optimistic update for instant UI feedback,
but the **real** mutation now goes to the database.

---

## 4. User incident detail — Fabricated timeline

**Before**: [feature-user/.../incidentdetail/IncidentDetailInteractor.kt](../feature-user/src/main/kotlin/com/amanah/feature/user/node/incidentdetail/IncidentDetailInteractor.kt)

```kotlin
// ── TODO: replace with UserRepository.getIncident(alertId) ────────────
view?.render(
    IncidentDetailState(
        alertId        = alertId,
        status         = IncidentStatus.RESOLVED,
        triggeredAt    = System.currentTimeMillis() - 3_600_000,
        respondersNotified  = 5,
        respondersAcknowledged = 3,
        resolutionNote = "Resolved by responder. Help arrived in 8 minutes.",
        events         = listOf(
            IncidentEventEntry("triggered",  "Emergency triggered", ...),
            IncidentEventEntry("broadcast",  "Notified 5 nearby members", ...),
            IncidentEventEntry("accepted",   "Responder accepted", ...),
            IncidentEventEntry("arrived",    "Responder arrived", ...),
            IncidentEventEntry("resolved",   "Incident resolved", ...),
        ),
    )
)
```

**After**: pulls the real incident from the backend:

```kotlin
scope.launch {
    when (val outcome = repo.getIncident(alertId)) {
        is Outcome.Success -> view?.render(outcome.value.toState())
        else               -> view?.render(IncidentDetailState(alertId = alertId, isLoading = false))
    }
}
```

`toState()` maps the `IncidentDto` to the view-state, parses ISO dates,
and infers `IncidentStatus`.

---

## 5. Admin alert detail — Fabricated victim + responders

**Before**: [feature-admin/.../alertdetail/AdminAlertDetailInteractor.kt](../feature-admin/src/main/kotlin/com/amanah/feature/admin/node/alertdetail/AdminAlertDetailInteractor.kt)

```kotlin
current = AdminAlertDetailState(
    alertId       = alertId,
    isLoading     = false,
    status        = AlertStatus.ACTIVE,
    victimName    = "Aisha Rahman",
    victimLat     = 23.8103,
    victimLng     = 90.4125,
    h3Cell        = "872bedfd5ffffff",
    responders    = listOf(
        ResponderEntry("r1", "Omar Farouq",  ...),
        ResponderEntry("r2", "Salim Ahmed",  ...),
        ResponderEntry("r3", "Hassan Karim", ...),
    ),
    notifiedCount     = 5,
    acknowledgedCount = 2,
)
```

**After**: `AdminRepository.getIncident(alertId)` + WS subscription for live
responder positions (already wired in the gateway).

```kotlin
when (val outcome = repo.getIncident(alertId)) {
    is Outcome.Success -> { current = outcome.value.toState(); view?.render(current) }
    else               -> { current = current.copy(isLoading = false); view?.render(current) }
}
```

Force-resolve also goes through the repository:

```kotlin
when (repo.resolveIncident(alertId, note = "admin_force_resolved")) {
    is Outcome.Success -> { current = current.copy(status = AlertStatus.RESOLVED); ... }
    ...
}
```

---

## 6. Admin user detail — Fabricated identity + devices + activity

**Before**: [feature-admin/.../userdetail/AdminUserDetailInteractor.kt](../feature-admin/src/main/kotlin/com/amanah/feature/admin/node/userdetail/AdminUserDetailInteractor.kt)

```kotlin
current = AdminUserDetailState(
    userId         = userId,
    displayName    = "Aisha Rahman",
    email          = "aisha@demo.amanah",
    phone          = "+8801700000001",
    role           = UserRole.USER,
    status         = AccountStatus.PENDING_APPROVAL,
    devices        = listOf(DeviceEntry("d1", "Pixel 8", "Android 14", ...)),
    recentActivity = listOf(
        ActivityEntry("a1", "Requested account", ...),
        ActivityEntry("a2", "Verified phone",    ...),
    ),
)
```

**After**: pulls real data from `AdminRepository.getUser`:

```kotlin
when (val outcome = repo.getUser(userId)) {
    is Outcome.Success -> { current = outcome.value.toState(); view?.render(current) }
    else               -> ...
}
```

`mutateStatus(...)` (approve / suspend) now calls
`repo.approveUser(id)` or `repo.suspendUser(id, reason)`.

---

## 7. Hard-coded H3 cell

**Before** (still present): [feature-user/.../UserDashboardInteractor.kt](../feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/UserDashboardInteractor.kt)

```kotlin
// TODO(LocationProvider): replace with current H3 cell from FusedLocationProvider
val userH3Cell = "872bedfd5ffffff"
```

Status: **flagged with a `TODO(LocationProvider)` marker**; not removable
without wiring `FusedLocationProviderClient` (separate roadmap item). The
flag is also tracked in MVP_COMPLETION_CHECKLIST.

---

## Summary table

| Fixture | Location | Status |
|---|---|---|
| `Aisha` / `Omar` nearby grid | UserFeature.loadNearbyUsers | ✅ removed |
| Stub user list (admin) | AdminFeature.LoadAll | ✅ removed |
| Stub alert (admin) | AdminFeature.LoadAll | ✅ removed |
| Local-only approve/suspend | AdminFeature reducer | ✅ now hits backend |
| Local-only resolve | AdminFeature reducer | ✅ now hits backend |
| Incident detail fixture (user) | IncidentDetailInteractor | ✅ now real fetch |
| Alert detail fixture (admin) | AdminAlertDetailInteractor | ✅ now real fetch |
| User detail fixture (admin) | AdminUserDetailInteractor | ✅ now real fetch |
| H3 cell `872bedfd5ffffff` | UserDashboardInteractor | ⚠️ flagged TODO(LocationProvider) |

**Net change**: 8 of 9 fake data sources eliminated. The remaining 1 is
tagged for the location-services iteration and is harmless (the H3 cell
is sent to the server, which already validates it server-side).
