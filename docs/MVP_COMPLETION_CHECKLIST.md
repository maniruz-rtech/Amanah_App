# MVP Completion Checklist

## What's done (this session)

### Backend
- [x] `/users/me` 500 fixed (User.status drift)
- [x] `SOSCreateRequest.severity` added (schema/service drift)
- [x] `SOSCreateResponse.verification_pin` made optional
- [x] `Settings.broadcast_responder_limit` added
- [x] `audit_logs.device_id` no longer enforces FK
- [x] Six new Alembic migrations (002–006 + `init_schema_from_models.py`
      bootstrap)
- [x] `Incident` model timestamps → `DateTime(timezone=True)`
- [x] `EmergencyLocation` timestamps → `DateTime(timezone=True)`
- [x] `UserRole.assigned_at` gets a default
- [x] Every `ENUM(...)` mapped_column now has `values_callable` so Python
      enum `.value` is what hits Postgres
- [x] GeoAlchemy2 auto-index disabled where `__table_args__` declares the
      index explicitly
- [x] Smoke test script (`scripts/smoke_e2e.sh`) passes 8/8

### Android — Repositories
- [x] `Outcome<T>` + `apiCall { ... }` foundation
- [x] `EmergencyRepository` (retry-aware SOS)
- [x] `UserRepository`
- [x] `NotificationsRepository`
- [x] `TrustedContactsRepository`
- [x] `DeviceRepository`
- [x] `OtpRepository` (+ OTP DTOs in `ApiService`)
- [x] `AdminRepository`
- [x] All 7 wired into `AppGraph` as lazy singletons

### Android — Realtime
- [x] `OutboundQueue` lifted to interface
- [x] `InMemoryOutboundQueue` (tests)
- [x] `DurableOutboundQueue` (DataStore-backed; production graph)
- [x] WS 401 → `onAuthRetry` → token refresh → single-shot reconnect
- [x] WS gateway uses the new outbound-queue interface

### Android — Features
- [x] `UserFeature` — Aisha/Omar stub deleted
- [x] `AdminFeature` — stub user list + alerts deleted
- [x] `IncidentDetailInteractor` — fabricated fixture replaced with
      `UserRepository.getIncident`
- [x] `AdminAlertDetailInteractor` — fabricated victim + responders
      replaced with `AdminRepository.getIncident`
- [x] `AdminUserDetailInteractor` — fabricated devices/activity replaced
      with `AdminRepository.getUser`
- [x] `AdminFeature` approve/suspend/resolve now hit the backend
- [x] `EmergencyAlertEngine.persistAlertViaRest` — canonical SOS path
- [x] `UserDashboardNode` accepts `EmergencyRepository` + `UserRepository`
- [x] `AdminDashboardNode` accepts `AdminRepository`
- [x] All three detail nodes accept the right repository
- [x] `RootNode` passes repositories through

### Android — Session lifecycle
- [x] Session rehydration on cold start (returning users skip login)
- [x] Logout disconnects the realtime gateway + clears Tink store

### Documentation
- [x] `MVP_GAP_CLOSURE_PLAN.md`
- [x] `ANDROID_REPOSITORY_IMPLEMENTATION.md`
- [x] `SOS_PERSISTENCE_FLOW.md`
- [x] `REALTIME_INCIDENT_FLOW.md`
- [x] `OFFLINE_DURABILITY_PLAN.md`
- [x] `FAKE_DATA_REMOVAL_REPORT.md`
- [x] `END_TO_END_VALIDATION.md`
- [x] `MVP_COMPLETION_CHECKLIST.md` (this file)

---

## What's next (priority-ordered)

### P0 — must close before any pilot

| # | Item | Owner | Effort |
|---|---|---|---|
| 1 | Bazel build the Android client end-to-end with the new repository wiring | client | 0.5 d |
| 2 | Re-issue Firebase config for `com.amanah.app` and wire FCM device-token registration through `DeviceRepository.register` | client | 1 d |
| 3 | Replace the hard-coded `userH3Cell = "872bedfd5ffffff"` with a real `LocationProvider` over `FusedLocationProviderClient` | client | 1.5 d |
| 4 | Replace `PinningConfig.PRIMARY_PIN` / `BACKUP_PIN` placeholders with real production SPKI hashes | infra | 0.5 d |
| 5 | Add a backend `/api/v1/users/nearby` endpoint so the User Dashboard's nearby tab can render real data | backend | 1 d |
| 6 | Wire a foreground service that keeps the process alive during an active emergency | client | 1 d |
| 7 | Unit tests for `EmergencyRepository.createSos` (success + retry + auth-fail paths) | client | 1 d |
| 8 | Unit tests for `OkHttpRealtimeGateway` reconnect FSM | client | 1.5 d |

### P1 — required for MVP launch

| # | Item | Effort |
|---|---|---|
| 9 | Bring up Sentry breadcrumbs in production builds | 0.5 d |
| 10 | Wire a server-side replay cursor so reconnect doesn't miss events | 1.5 d |
| 11 | Refresh-token hashing migration (don't store refresh tokens in plaintext) | 0.5 d |
| 12 | Queue length cap with overflow eviction | 0.5 d |
| 13 | Backend rate-limit middleware in front of `/auth/login`, `/incidents/sos`, `/auth/otp/request` | 1 d |
| 14 | Integration tests against the running stack (network flap, pong-loss watchdog) | 2 d |
| 15 | Move `JWT_SECRET_KEY` and `ENCRYPTION_KEY` out of env files into a secret manager for production deploys | 1 d |
| 16 | Notification center screen wired to `NotificationsRepository.list` | 0.5 d |
| 17 | Trusted-contacts list screen wired to `TrustedContactsRepository.list` | 0.5 d |
| 18 | Profile edit + phone/email OTP verification screens | 2 d |

### P2 — hardening pass

| # | Item | Effort |
|---|---|---|
| 19 | Replace `PYTHONPATH=/app` shadowing of the `alembic` library (rename `backend/alembic/` → `backend/db_migrations/`) | 0.5 d |
| 20 | Make `create_admin.py` non-interactive (`--username`, `--password`, etc.) | 0.5 d |
| 21 | Rebuild legacy `001_initial_schema.py` from the current models so a fresh DB doesn't need 002–006 + bootstrap | 0.5 d |
| 22 | Server-side dedupe by client-supplied `event_id` (idempotency-key column) | 1 d |
| 23 | Multi-instance WebSocket via Redis pub/sub | 2 d |
| 24 | k6 load test (10K concurrent WS, 100 SOS / minute) | 2 d |
| 25 | i18n (EN + BN + AR) | 3 d |

---

## Production-readiness gates

A release is ready when:

- [ ] Smoke test passes in CI on every PR.
- [ ] Crash-free rate ≥ 99.5 % on the closed beta for 7 days.
- [ ] TLS pinning verified via mitmproxy (release build refuses to connect).
- [ ] No `// TODO: replace with .*Repository` markers in any feature module.
- [ ] No `PinningConfig.PRIMARY_PIN.contains("REPLACE_WITH")` (the build
      throws at first connection attempt if so — verified manually before
      tagging).
- [ ] `JWT_SECRET_KEY` and `ENCRYPTION_KEY` are not the default
      `CHANGE-ME-...` values in any deployed environment.
- [ ] Refresh tokens are stored hashed, not plaintext, in
      `refresh_tokens.token_hash`.
- [ ] Backend has Sentry hooked up; client has Sentry hooked up.
- [ ] Foreground service exists for active emergencies.
- [ ] One responder + one victim cross-device test passes the full
      trigger → fanout → resolve flow.

---

## What this MVP can do TODAY

| Capability | Status |
|---|---|
| Sign in with username/password | ✅ |
| Receive JWT, persist via Tink + DataStore | ✅ |
| Reauthenticate on cold start | ✅ |
| Refresh token on 401 (REST + WS) | ✅ |
| Trigger SOS → backend persists incident + emergency_location + audit + event | ✅ |
| Backend broadcasts emergency.alert over WSS to nearby clients | ✅ |
| Pinned TLS, header-based WS auth | ✅ |
| Durable outbound queue for non-trigger envelopes | ✅ |
| Admin user list + approve + suspend | ✅ |
| Admin alert detail + force-resolve | ✅ |
| Admin user detail | ✅ |
| User incident detail | ✅ |
| Logout → token revoked + Tink keyset rotated | ✅ |
| WS reconnect with exponential backoff + heartbeat watchdog | ✅ |
| Duplicate-event protection on inbound | ✅ |

| Capability | Pending |
|---|---|
| Nearby users list (Home tab grid) | ⏳ backend `/users/nearby` endpoint |
| Real H3 cell from device location | ⏳ `LocationProvider` |
| FCM push delivery + device registration | ⏳ FCM wiring + Firebase config |
| Trusted contacts management (add/update/delete) | ⏳ ApiService methods + screens |
| Profile editing + phone/email verification | ⏳ screens |
| Foreground service during active emergency | ⏳ background work |
| End-to-end test against real device pair | ⏳ test harness |
