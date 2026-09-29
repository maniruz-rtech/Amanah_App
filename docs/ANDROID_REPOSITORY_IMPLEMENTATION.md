# Android Repository Architecture

## Overview

Every Android feature reaches the backend through a thin **repository**
layer. The contract:

- Repositories own all Retrofit calls. No `ApiService` references leak
  into Features, Interactors, or Views.
- Repositories **never throw**. Every public method returns
  `Outcome<T>` — a sealed result type that callers `when`-pattern on.
- Repositories are stateless **except** for retry policies that are
  internal to the method (EmergencyRepository's SOS path).
- One repository per resource domain (Auth, User, Emergency, Admin,
  Notifications, TrustedContacts, Device, Otp).

```
Feature (MVICore)        Interactor               Repository       ApiService
─────────────────        ──────────               ──────────       ──────────
emit Wish ─────────► onAttach() launches  ─► suspend method ─► HTTP call (Retrofit)
                     coroutine that         (returns Outcome)   │
state ← reduce ◄──── pushes Outcome back ◄────────────────────  ▼
                     into the feature via                   asyncpg + Postgres
                     a follow-up Wish
```

## `Outcome<T>` — the shared result type

File: [feature-core/repository/Outcome.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/repository/Outcome.kt)

```kotlin
sealed class Outcome<out T> {
    data class Success<T>(val value: T) : Outcome<T>()
    object NetworkDown : Outcome<Nothing>()
    object AuthFailed  : Outcome<Nothing>()
    data class ServerError(val code: Int, val message: String?) : Outcome<Nothing>()
    data class Unexpected(val cause: Throwable) : Outcome<Nothing>()
}
```

Why not `kotlin.Result`: it doesn't differentiate AuthFailed from
NetworkDown. For an emergency app the call site needs to make different
decisions for "retry later" vs. "you need to log back in" vs. "validation
failed."

`apiCall { ... }` is a one-liner wrapper that maps exceptions to the
correct subclass:
- `HttpException(401|403)` → `AuthFailed`
- `HttpException(other)`   → `ServerError(code, message)`
- `IOException`            → `NetworkDown`
- everything else          → `Unexpected(cause)`

## Per-repository surface

### EmergencyRepository ([file](../feature-emergency/src/main/kotlin/com/amanah/feature/emergency/repository/EmergencyRepository.kt))

The canonical persistence path for the SOS lifecycle.

| Method | Endpoint | Retry policy |
|---|---|---|
| `createSos(lat, lng, ...)` | POST /api/v1/incidents/sos | Up to 4 attempts; backs off 500 ms → 1s → 2s → 4s on NetworkDown or ServerError 5xx. Auth-fail short-circuits. |
| `pushLocation(id, lat, lng, ...)` | POST /api/v1/incidents/{id}/location | Single attempt. |
| `cancel(id, reason)` | POST /api/v1/incidents/{id}/cancel | Single attempt. |
| `resolve(id, note)` | POST /api/v1/incidents/{id}/resolve | Single attempt. |
| `getIncident(id)` | GET /api/v1/incidents/{id} | Single attempt. |
| `listMyActive()` | GET /api/v1/incidents/my/active | Single attempt. |

### UserRepository ([file](../feature-user/src/main/kotlin/com/amanah/feature/user/repository/UserRepository.kt))

| Method | Endpoint |
|---|---|
| `me()` | GET /api/v1/users/me |
| `updateMe(name?, email?, phone?)` | PATCH /api/v1/users/me |
| `listMyActiveIncidents()` | GET /api/v1/incidents/my/active |
| `getIncident(id)` | GET /api/v1/incidents/{id} |

### NotificationsRepository ([file](../feature-user/src/main/kotlin/com/amanah/feature/user/repository/NotificationsRepository.kt))

| Method | Endpoint |
|---|---|
| `list(skip, limit)` | GET /api/v1/notifications |
| `markRead(ids)` | POST /api/v1/notifications/mark-read |
| `markAllRead()` | POST /api/v1/notifications/mark-all-read |
| `unreadCount()` | GET /api/v1/notifications/unread-count |

### TrustedContactsRepository ([file](../feature-user/src/main/kotlin/com/amanah/feature/user/repository/TrustedContactsRepository.kt))

| Method | Endpoint |
|---|---|
| `list()` | GET /api/v1/users/trusted-contacts |

(Add/update/delete are scaffolded server-side and pending in `ApiService`.)

### DeviceRepository ([file](../feature-user/src/main/kotlin/com/amanah/feature/user/repository/DeviceRepository.kt))

| Method | Endpoint |
|---|---|
| `register(uuid, fcmToken, model?, os?)` | POST /api/v1/users/devices |
| `revoke(deviceId)` | DELETE /api/v1/users/devices/{id} |

### OtpRepository ([file](../feature-auth/src/main/kotlin/com/amanah/feature/auth/repository/OtpRepository.kt))

| Method | Endpoint |
|---|---|
| `request(channel, purpose, recipient)` | POST /api/v1/otp/request |
| `verify(otpId, code)` | POST /api/v1/otp/verify |
| `resend(otpId)` | POST /api/v1/otp/resend |

### AdminRepository ([file](../feature-admin/src/main/kotlin/com/amanah/feature/admin/repository/AdminRepository.kt))

| Method | Endpoint |
|---|---|
| `listUsers(skip, limit)` | GET /api/v1/admin/users |
| `getUser(id)` | GET /api/v1/admin/users/{id} |
| `approveUser(id)` | POST /api/v1/admin/users/{id}/approve |
| `suspendUser(id, reason)` | POST /api/v1/admin/users/{id}/suspend |
| `getIncident(id)` | GET /api/v1/incidents/{id} |
| `resolveIncident(id, note?)` | POST /api/v1/incidents/{id}/resolve |
| `listAuditLogs(skip, limit)` | GET /api/v1/admin/audit-logs |
| `listApprovals(skip, limit)` | GET /api/v1/admin/approvals |

### AuthRepository (existing, unchanged shape)

| Method | Endpoint |
|---|---|
| `login(email, password)` | POST /api/v1/auth/login |
| `requestPasswordReset(usernameOrEmail)` | POST /api/v1/auth/password-reset/request |

## Threading + scopes

Each repository creates a private `CoroutineScope(SupervisorJob() +
Dispatchers.IO)` only when it needs background work (currently
`AuthRepository` for Reaktive bridging). Most methods are pure `suspend` and
defer scope ownership to the caller (typically the Interactor).

## Wiring into MVICore Features

Pattern used in `UserDashboardInteractor` / `AdminDashboardInteractor`:

```kotlin
override fun onAttach() {
    feature.states.subscribe { view?.render(it) }.autoDispose()
    feature.news.subscribe { /* route news */ }.autoDispose()
    view?.events = { wish -> feature.accept(wish) }

    repository?.let { loadInitial(it) }
}

private fun loadInitial(repo: UserRepository) {
    scope.launch {
        when (val outcome = repo.me()) {
            is Outcome.Success     -> feature.accept(UserWish.MeLoaded(outcome.value))
            Outcome.AuthFailed     -> feature.accept(UserWish.LoadFailed("auth"))
            Outcome.NetworkDown    -> feature.accept(UserWish.LoadFailed("offline"))
            is Outcome.ServerError -> feature.accept(UserWish.LoadFailed("server"))
            is Outcome.Unexpected  -> feature.accept(UserWish.LoadFailed("unexpected"))
        }
    }
}
```

This keeps the MVI Actor a pure function of (state, wish) → effect — no
side-effecting `subscribe` lambdas inside the Actor.

## Testing

Each repository is unit-testable with MockK on the JVM:

```kotlin
@Test fun `createSos returns Success when API returns 201`() = runTest {
    val api = mockk<ApiService>()
    coEvery { api.createSos(any()) } returns IncidentDto(...)
    val repo = EmergencyRepository(api)

    val outcome = repo.createSos(lat = 23.81, lng = 90.41)

    assertIs<Outcome.Success<IncidentDto>>(outcome)
}

@Test fun `createSos retries on NetworkDown`() = runTest {
    val api = mockk<ApiService>()
    coEvery { api.createSos(any()) } throws IOException("no net") andThen IncidentDto(...)
    val repo = EmergencyRepository(api)

    val outcome = repo.createSos(lat = 23.81, lng = 90.41)

    assertIs<Outcome.Success<IncidentDto>>(outcome)
    coVerify(exactly = 2) { api.createSos(any()) }
}
```

(Tests not yet committed — tracked in MVP_COMPLETION_CHECKLIST.)
