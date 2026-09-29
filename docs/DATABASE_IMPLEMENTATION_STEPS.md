# Database Implementation Steps

Concrete plan with files, order, and effort. Everything below is what's left
between "the audit" and "the project is genuinely connected end-to-end."

---

## 0. Effort summary

```
Backend work     :  ~2 days  (1 engineer)
Android repos    :  ~5 days  (1 engineer)
Android cache    :  ~2 days
Wiring + tests   :  ~2 days
                   ────────
Total            :  ~11 working days for 1 engineer
                   ────────
With 2 engineers in parallel:  ~6 working days
```

---

## 1. Backend — small targeted changes (day 1–2)

### 1.1 Add `backend/.env.example`
Documented env contract. ([POSTGRESQL_INTEGRATION_PLAN.md §4.1](POSTGRESQL_INTEGRATION_PLAN.md))

### 1.2 Patch `/health` to probe the DB
File: `backend/app/api/v1/health.py`.
- Replace the unconditional 200 with a `SELECT 1` probe.
- Return 503 on DB failure.
- Add a `redis_ok` check while we're there.

### 1.3 Run `alembic upgrade head` automatically on container boot
File: `backend/docker-compose.yml`.
- Either inline (`bash -c "alembic upgrade head && uvicorn ..."`)
- Or add a `migrate` service with `depends_on` and `restart: 'no'`.

### 1.4 Add `GET /api/v1/users/nearby`
- New repository method `UserRepository.get_active_in_h3_kring(h3_cell, k)`.
- New schema `NearbyUserResponse`.
- New endpoint in `app/api/v1/users.py`.
- Requires adding `users.last_h3_cell_district` (varchar(16), indexed) and
  `users.last_h3_cell_block` (varchar(16)) — one Alembic revision.

### 1.5 Fix `websocket_v2._handle_emergency_alert`
- **Choice A (recommended):** return an error envelope `{"type":"error","payload":{"reason":"use_rest"}}`. Force the client onto REST.
- **Choice B:** call `IncidentService.create_sos(jwt_user_id, payload)`.

### 1.6 Fix `websocket_v2._handle_presence`
- UPDATE `users.last_h3_cell_district = $1`, `last_seen_at = now()`.

### 1.7 Refresh-token hashing migration
- Add `refresh_tokens.token_hash` column.
- Repository: hash on insert, lookup-by-hash on verify (constant-time).
- One Alembic revision. Existing rows are invalidated — acceptable.

### 1.8 CI workflow
- GitHub Actions: spin postgis service, run `alembic upgrade head`, run pytest.
- Reject commits where `JWT_SECRET_KEY` / `ENCRYPTION_KEY` defaults appear in env files.

---

## 2. Android — repositories (day 3–7)

Each repository follows the same pattern, mirrored on `AuthRepository`:

```kotlin
class XxxRepository(
    private val api: ApiService,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO),
) {
    fun foo(...): Observable<FooResult> = observable { emitter ->
        scope.launch {
            try { ... api.foo(...) ... emitter.onNext(...) } catch (e) { ... }
        }
    }
}
```

### 2.1 `feature-user/repository/UserRepository.kt`
Methods:
- `getMe(): Observable<UserProfile>`
- `updateMe(req): Observable<UserProfile>`
- `listNearbyActive(): Observable<List<NearbyUser>>`
- `listMyActiveIncidents(): Observable<List<IncidentSummary>>`
- `getIncident(id): Observable<IncidentDetail>`

### 2.2 `feature-user/repository/TrustedContactsRepository.kt`
- `list(): Observable<List<TrustedContact>>`
- `add(req): Observable<TrustedContact>`
- `update(id, req)`
- `delete(id)`

### 2.3 `feature-user/repository/DeviceRepository.kt`
- `register(req: DeviceRegistration)`
- `list()`
- `revoke(id)`

### 2.4 `feature-emergency/repository/EmergencyRepository.kt`
Methods:
- `createSos(SosRequest): Observable<IncidentDto>`        ◀── this is the key new path
- `pushLocation(incidentId, LocationUpdate)`
- `cancel(incidentId, reason): Observable<IncidentDto>`
- `resolve(incidentId, note): Observable<IncidentDto>`

### 2.5 `feature-admin/repository/AdminRepository.kt`
Methods:
- `listUsers(skip, limit): Observable<PaginatedResponse<UserProfile>>`
- `getUser(id)`
- `approveUser(id)` / `suspendUser(id, reason)`
- `listIncidents(skip, limit)`
- `getIncident(id)`
- `resolveIncident(id, note)`
- `listAuditLogs(skip, limit)`
- `listApprovals(skip, limit)`

### 2.6 `feature-core/repository/NotificationsRepository.kt`
- `list(skip, limit)`
- `markRead(ids: List<String>)`
- `markAllRead()`
- `unreadCount(): Observable<Int>`

### 2.7 `feature-auth/repository/OtpRepository.kt`
- `request(channel, recipient)`
- `verify(otpId, code)`
- `resend(otpId)`

### 2.8 `feature-auth/repository/AuthRepository.kt` (extend existing)
Add:
- `logout(refreshToken)` → `POST /api/v1/auth/logout`
- `refresh(refreshToken)` (already in interceptor)

---

## 3. Android — wire features to repositories (day 7–9)

For each feature replace the stub:

### 3.1 `UserFeature.loadNearbyUsers` (`feature-user/.../UserFeature.kt:151-164`)
Replace the stub with an injected `UserRepository.listNearbyActive()` call:

```kotlin
class UserFeature(
    private val userRepo: UserRepository? = null,   // null = preview/test mode
) : BaseFeature<...>( ...
    actor = UserActor(userRepo), ...
)

private class UserActor(private val userRepo: UserRepository?) : Actor<...> {
    private fun loadNearbyUsers(): Observable<UserEffect> = observable { emitter ->
        emitter.onNext(UserEffect.NearbyLoading)
        if (userRepo == null) {
            emitter.onNext(UserEffect.NearbyLoaded(emptyList()))
        } else {
            userRepo.listNearbyActive().subscribe(
                onNext = { users -> emitter.onNext(UserEffect.NearbyLoaded(users.map { it.toDomain() })) },
                onError = { emitter.onNext(UserEffect.NearbyLoaded(emptyList())) },
            )
        }
        emitter.onComplete()
    }
}
```

Wire from `UserDashboardNode` (which is built by `RootNode.showUserDashboard`) — pass the repo from `AppGraph.userRepository`.

### 3.2 `EmergencyAlertEngine` outbound path
Currently calls `wsPublish(EmergencyAlertMessage)`. Change to:

```kotlin
// in UserDashboardInteractor.publishEmergencyAlert
emergencyRepository.createSos(SosRequest(lat = msg.lat, lng = msg.lng, ...))
    .subscribe(
        onNext = { incident ->
            // Server has now persisted + broadcast.
            // Local engine moves to AlertConfirmed.
            engine.onIncomingAlert(toEmergencyAlertMessage(incident))
        },
        onError = { /* surface to user via snackbar */ },
    )
```

Delete the WS `EMERGENCY_ALERT` envelope send path. WS is now inbound-only for emergency.

### 3.3 `AdminFeature.LoadAll`
Replace stub generation with `adminRepo.listUsers()` + `adminRepo.listIncidents()`.

### 3.4 `AdminAlertDetailInteractor` / `AdminUserDetailInteractor` / `IncidentDetailInteractor`
Each fabricates a fixture. Replace with the appropriate repo call.

### 3.5 Session rehydration on cold start
In `RootNode.onAttach` (or its successor):

```kotlin
fun onAttach() {
    splashNode.performAttach()
    // After splash animation, decide route based on token presence
}

private fun onSplashFinished() {
    splashNode.performDetach()
    if (graph.tokenStore.hasSession() && !onboardingShown) {
        // returning user — try to hydrate via /users/me
        graph.userRepository.getMe().subscribe(
            onNext = { user -> showUserOrAdminDashboard(user) },
            onError = { showLogin() },
        )
    } else if (!onboardingShown) {
        onboardingNode.performAttach()
        _screen = Screen.Onboarding
    } else {
        showLogin()
    }
}
```

### 3.6 Wire WS 401 → token refresh
In `OkHttpRealtimeGateway.onFailure`, before `Terminated(AUTH_REJECTED)`, attempt a refresh: trigger a synthetic REST call (which will go through `RefreshInterceptor`) and reconnect on success.

Or, simpler: when `Terminated(AUTH_REJECTED)`, call `authRepository.refreshSession()` once and `gateway.connect()` again. If that also fails, then log the user out.

### 3.7 LocationProvider
Replace the hard-coded `"872bedfd5ffffff"` with a real implementation backed by `FusedLocationProviderClient`. Wrap in `LocationProvider.currentH3Cell()` returning a `Single<String>`.

---

## 4. Android — offline cache (day 9–10)

Add a small Room database with three tables — enough to keep "last seen"
state offline.

### 4.1 Room dependency

Add to `MODULE.bazel`:
```
"androidx.room:room-runtime:2.6.1",
"androidx.room:room-ktx:2.6.1",
"androidx.room:room-compiler:2.6.1",
```

### 4.2 Tables

```
@Entity table CachedIncident      (id, status, severity, started_at, lat, lng,
                                   updated_at)
@Entity table CachedNotification  (id, type, title, body, read, created_at)
@Entity table CachedNearbyUser    (user_id, display_name, h3_cell, last_seen_at)
```

### 4.3 Repository pattern

Each repository becomes "fetch from cache → emit → kick off network → on
success, update cache → emit again". Standard offline-first pattern.

### 4.4 Outbound queue durability

Replace `OutboundQueue` (in-memory) with DataStore-Proto-backed FIFO. Schema:

```proto
message QueuedEnvelope {
    string event_id = 1;
    string type     = 2;
    int64  enqueued_at_ms = 3;
    int64  ttl_ms   = 4;
    string payload_json = 5;
}

message OutboundQueueProto {
    repeated QueuedEnvelope entries = 1;
}
```

On gateway start: deserialize, drain TTL-expired entries, push survivors back into the in-memory queue. Periodic snapshot back to disk after each modification.

---

## 5. Files to create (concrete list)

```
NEW BACKEND
  backend/.env.example
  backend/alembic/versions/002_users_h3_cells.py        (h3 cell columns)
  backend/alembic/versions/003_incident_idempotency.py  (optional)
  backend/alembic/versions/004_refresh_token_hash.py    (refresh-token hashing)
  backend/app/repositories/user.py                       (add get_active_in_h3_kring)
  backend/app/api/v1/users.py                            (add /users/nearby)
  backend/app/api/v1/health.py                           (real DB probe)
  backend/app/websocket_v2.py                            (handler delegation or rejection)
  .github/workflows/backend.yml                          (CI)

NEW ANDROID
  feature-user/repository/UserRepository.kt
  feature-user/repository/TrustedContactsRepository.kt
  feature-user/repository/DeviceRepository.kt
  feature-emergency/repository/EmergencyRepository.kt
  feature-admin/repository/AdminRepository.kt
  feature-core/repository/NotificationsRepository.kt
  feature-auth/repository/OtpRepository.kt
  feature-core/location/LocationProvider.kt              (FusedLocationProviderClient wrapper)
  feature-core/cache/AmanahDatabase.kt                   (Room)
  feature-core/cache/Dao{Incident,Notification,NearbyUser}.kt
  feature-core/cache/Entity{Incident,Notification,NearbyUser}.kt
  feature-core/realtime/DurableOutboundQueue.kt          (DataStore-Proto backed)
  feature-core/realtime/OutboundQueueProto.proto         (Proto-DataStore schema)
```

## 6. Files to modify

```
backend/docker-compose.yml          (run alembic on boot)
backend/Makefile                    (add seed-demo)

app/di/AppGraph.kt                  (build the new repos)
app/node/RootNode.kt                (session rehydration on cold start)

feature-user/.../UserFeature.kt
feature-user/.../UserDashboardInteractor.kt
feature-user/.../UserDashboardNode.kt
feature-user/.../incidentdetail/IncidentDetailInteractor.kt

feature-admin/.../AdminFeature.kt
feature-admin/.../alertdetail/AdminAlertDetailInteractor.kt
feature-admin/.../userdetail/AdminUserDetailInteractor.kt

feature-emergency/.../EmergencyAlertEngine.kt          (drop wsPublish; use repo)

feature-core/realtime/OkHttpRealtimeGateway.kt         (WS 401 → refresh attempt)

MODULE.bazel                                            (add Room)
feature-core/BUILD.bazel                                (Room deps)
feature-user/BUILD.bazel                                (Room deps if dao lives here)
```

---

## 7. Implementation order (parallelisable)

```
DAY 1  ─  Backend: .env.example, health probe, alembic-on-boot, users.last_h3_cell migration
DAY 2  ─  Backend: /users/nearby endpoint, websocket_v2 fix, refresh-token hash migration, CI
DAY 3  ─  Android: UserRepository, NotificationsRepository, DeviceRepository
DAY 4  ─  Android: EmergencyRepository (REST-driven SOS); rewrite EmergencyAlertEngine outbound path
DAY 5  ─  Android: AdminRepository, OtpRepository, TrustedContactsRepository
DAY 6  ─  Android: wire UserFeature + AdminFeature to repos; replace fixture interactors
DAY 7  ─  Android: session rehydration, LocationProvider, WS 401 → refresh
DAY 8  ─  Android: Room cache layer (read-through)
DAY 9  ─  Android: durable OutboundQueue (DataStore-Proto)
DAY 10 ─  E2E test: docker-compose up → seed demo → manual demo flow
DAY 11 ─  Polish + smoke instrumentation + audit-doc updates
```

Steps 1–2 (backend) can run in parallel with 3–6 (Android repos) because all
the endpoints needed already exist on the backend. The Android team can wire
against the current backend and pick up the new `/users/nearby` once it lands.

---

## 8. Acceptance criteria

The implementation is "done" when every line below is true on a fresh
checkout:

- [ ] `docker-compose up -d` brings up postgis, redis, fastapi, celery in < 60 s.
- [ ] `curl http://localhost:8000/api/v1/health` returns 200 with `{"db":"up", ...}`.
- [ ] `make seed-demo` creates 1 org, 1 region, admin + user accounts.
- [ ] `bazel build //app:amanah --compilation_mode=opt` succeeds.
- [ ] Cold install → login → User dashboard shows real `/users/me` data.
- [ ] Nearby tab shows users seeded by `make seed-demo` (after they ping presence).
- [ ] Long-press emergency button creates an `incidents` row visible via psql:
  `SELECT id, status FROM incidents ORDER BY created_at DESC LIMIT 1;`
- [ ] Same trigger creates a `audit_logs` row with action `sos_created`.
- [ ] On a second device with admin role, the new alert appears in the Alerts tab via WS push within 2 s.
- [ ] `tail -f` of celery logs shows no errors.
- [ ] `psql -c "EXPLAIN ANALYZE SELECT * FROM users WHERE last_h3_cell_district = '872bedfd5ffffff';"` uses an index (< 5 ms).
- [ ] Kill the Android app during an active emergency → restart → emergency state restored from cache.
- [ ] Logout → Tink keyset rotated → relaunch → forced re-login.

If any line is false, that's a P1 to close before declaring "connected."
