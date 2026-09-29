# Database Connection Audit

**Date:** 2026-05-21
**Scope:** Independent verification of whether the database layer is genuinely connected and operational, end-to-end, across the Amanah platform.
**Auditor stance:** A repository file existing does **not** mean the DB is connected. A model file existing does **not** mean it persists. We only mark a path as "connected" when there is a verified chain `caller → ORM → connection-pool → migrated table`.

---

## 1. Executive Summary

| Layer | Status | Verdict |
|---|---|---|
| PostgreSQL container, PostGIS | ✅ Configured | `docker-compose up db` brings up `postgis/postgis:16-3.4` with healthcheck. |
| SQLAlchemy async engine | ✅ Real | `create_async_engine` over asyncpg with pool config, pre-ping enabled. |
| Alembic | ✅ Real | One revision (`001_initial_schema.py`, 379 lines) covers 18 tables + PostGIS extension. |
| Backend repositories | ✅ Real | Concrete SQL via `select(...)`, `db.add(...)`, `db.flush(...)`, `db.refresh(...)`. |
| Backend services | ✅ Real | `IncidentService` and peers compose multiple repositories per transaction. |
| Backend REST APIs | ✅ Real | `POST /incidents/sos` runs the full persistence chain. |
| Backend WebSocket | ❌ **In-memory only** | `ConnectionManager` is a `dict`; no handler writes to the DB. |
| Android auth flow | ✅ Real | `AuthRepository.login → ApiService.login → POST /auth/login → User row`. |
| Android non-auth features | ❌ **Stub data** | `UserFeature`, `AdminFeature`, three detail interactors all return hard-coded fixtures. |
| Android emergency SOS path | ❌ **Lossy** | Client uses WS envelope; backend WS handler is a TODO; no DB row created. |
| Android offline cache | ❌ **None** | No Room, no DataStore-Proto, no LRU. Every refresh hits the network. |
| Outbound queue durability | ⚠️ **In-memory** | `OutboundQueue` is `ConcurrentLinkedDeque`; lost on process death. |
| Token storage | ✅ Real | Tink AEAD + DataStore + Keystore-wrapped master key. |

**Bottom-line:** the project has a production-grade database and persistence layer on the backend, but **only one of its many features is actually using it**. The realtime channel is *transport-only* — events are routed but not stored. The Android client is *RPC-stubbed* for everything except auth.

This is fixable in 2–3 engineer-weeks. See [DATABASE_IMPLEMENTATION_STEPS.md](DATABASE_IMPLEMENTATION_STEPS.md).

---

## 2. Current Database Status

### Configuration (backend/app/core/config.py)
- `database_url: PostgresDsn` from env (default `postgresql+asyncpg://amanah:amanah@localhost:5432/amanah`).
- `database_pool_size: 20`, `database_max_overflow: 20`, `database_pool_timeout: 30`.
- `database_echo: false` (debug log toggle).

### Engine + sessionmaker (backend/app/db/session.py)
- `create_async_engine(..., pool_pre_ping=True)` — survives connection idleness behind PgBouncer/LB.
- `async_sessionmaker(class_=AsyncSession, expire_on_commit=False)`.
- `get_db()` dependency commits on success, rolls back on exception, closes always. Mounted as `DBSession` in FastAPI's `Annotated[AsyncSession, Depends(get_db)]`.

### Migrations (backend/alembic/)
- `alembic.ini` configured; `env.py` loads from `settings.database_url` (no separate `sqlalchemy.url`).
- `versions/001_initial_schema.py` (379 lines):
  - Enables `postgis` extension.
  - Creates 18 tables: organizations, regions, users, roles, user_roles, devices, trusted_contacts, responder_status, incidents, emergency_locations, incident_assignments, incident_events, notifications, otp_requests, password_reset_requests, refresh_tokens, admin_approvals, audit_logs.
  - Includes proper FK constraints, indices, and a `Geography(POINT)` column on `emergency_locations.location`.

### Connection pool
- 20 + 20 connections per backend instance. Single instance OK for demo; for production multi-instance, configure PgBouncer.

### Transactions
- Per-request transaction via `get_db()`. Composite services (e.g. SOS create) keep the whole thing in one transaction. The pattern `db.add → db.flush → db.refresh` is correct for SQLAlchemy 2.0 async.

### Verdict
**Backend DB layer = production-quality.** Nothing to fix here.

---

## 3. Backend Connection Findings

### What works (verified by inspection)

| Endpoint | Service | Repository | DB action |
|---|---|---|---|
| `POST /api/v1/auth/login` | `AuthService.login` | `UserRepository.find_by_username/email`, `RefreshTokenRepository.create` | SELECT + INSERT |
| `POST /api/v1/incidents/sos` | `IncidentService.create_sos` | `IncidentRepository.create_sos`, `AuditLogRepository.log_action` | INSERT incident + emergency_location (PostGIS) + incident_event + audit_log |
| `POST /api/v1/incidents/{id}/location` | `IncidentService.update_location` | `IncidentRepository.add_location` | INSERT emergency_location + incident_event |
| `POST /api/v1/incidents/{id}/cancel` | `IncidentService.cancel` | `IncidentRepository.update_status` | UPDATE incidents (with state-machine validation) + INSERT incident_event |
| `GET /api/v1/users/me` | dependency chain | `UserRepository.get_by_id` | SELECT |
| `GET /api/v1/admin/users` | `AdminService.list_users` | `UserRepository.get_all` | SELECT (paginated) |
| `GET /api/v1/notifications` | `NotificationService.list` | `NotificationRepository` | SELECT (paginated) |
| `POST /api/v1/notifications/mark-read` | `NotificationService.mark_read` | `NotificationRepository.mark_read` | UPDATE |

Sample verification — `IncidentRepository.create_sos` ([backend/app/repositories/incident.py:41-102](../backend/app/repositories/incident.py#L41-L102)) writes three rows in one transaction: `incidents`, `emergency_locations` (with `ST_SetSRID(ST_MakePoint(lng, lat), 4326)` — real PostGIS geography), and `incident_events` (CREATED event). The service then writes a fourth row to `audit_logs`. All in a single transaction.

### What does NOT persist (verified by inspection)

**WebSocket handlers do not write to the DB.**

- `backend/app/websocket.py` `ConnectionManager` is an in-process Python `dict[user_id → list[WebSocket]]`. It broadcasts; it does not persist.
- `backend/app/websocket_v2.py` (the new header-auth endpoint) routes `emergency.alert` envelopes to `_handle_emergency_alert(user_id, payload)` — which is currently a `TODO` (only an `ainfo` log).
- `responder.location` updates received over WS are fanned out via `manager.broadcast_location_update(...)` — which does NOT write to `emergency_locations`. Only the REST path does.
- ACK envelopes are sent back to the client transport-only; no DB persistence.

**Consequence:** an emergency triggered via the WS channel today produces:
- ✅ A delivered notification to other connected users.
- ❌ Zero rows in `incidents`, `emergency_locations`, `incident_events`, `audit_logs`.

The DB has no idea the emergency happened.

---

## 4. API Persistence Findings

| API surface | Backend persists? | Client calls it? |
|---|---|---|
| `/api/v1/auth/*` | ✅ Yes | ✅ Yes (AuthRepository) |
| `/api/v1/incidents/sos` | ✅ Yes | ❌ **No** — client sends WS envelope instead |
| `/api/v1/incidents/{id}` | ✅ Yes | ❌ No — IncidentDetail uses fixture |
| `/api/v1/incidents/{id}/location` | ✅ Yes | ❌ No |
| `/api/v1/incidents/{id}/cancel` | ✅ Yes | ❌ No |
| `/api/v1/incidents/my/active` | ✅ Yes | ❌ No — alert history uses UserFeature stub |
| `/api/v1/users/me` | ✅ Yes | ❌ No |
| `/api/v1/users/devices` | ✅ Yes | ❌ No |
| `/api/v1/users/trusted-contacts` | ✅ Yes | ❌ No |
| `/api/v1/notifications` | ✅ Yes | ❌ No |
| `/api/v1/admin/users` | ✅ Yes | ❌ No — AdminFeature stub |
| `/api/v1/admin/users/{id}/approve` | ✅ Yes | ❌ No — button wires to MVI only |
| `/api/v1/admin/users/{id}/suspend` | ✅ Yes | ❌ No |
| `/api/v1/admin/audit-logs` | ✅ Yes | ❌ No |
| **`/api/v1/users/nearby`** | ❌ **does not exist** | Client expects it |

The single biggest *backend* gap is that there is no endpoint to fetch "members nearby this user's H3 cell" — which the client UI assumes. Without it, even after wiring the client repos, the Home tab's nearby grid cannot become real. Server-side work needed: a `UserRepository.get_active_users_in_h3_kring(...)` + endpoint.

---

## 5. Android Integration Findings

### Real wiring
- `AuthRepository` — calls Retrofit `ApiService.login(...)` → POST /auth/login → backend → persisted user row → returned JWT stashed in `TinkTokenStore`.
- `ApiService` (Retrofit interface) declares ~25 endpoints with the right paths and Gson-mapped DTOs.
- `AuthInterceptor` injects `Authorization: Bearer …` on all non-public endpoints.
- `RefreshInterceptor` does single-flight 401 → refresh → retry-once → on-second-401 sign-out.
- `TinkTokenStore` persists tokens via Tink AEAD over DataStore.

### Missing repositories
Only `AuthRepository` exists. The following are referenced by features (often as `// TODO: replace with ...Repository.X()` markers) but **do not exist**:
- `UserRepository` — getMe, updateMe, listNearbyActiveUsers, getAlertHistory
- `EmergencyRepository` — createSos, getIncident, pushLocation, cancel, resolve
- `AdminRepository` — listUsers, getUser, approve, suspend, listAlerts, listAuditLogs
- `NotificationsRepository` — list, markRead, markAllRead, unreadCount
- `TrustedContactsRepository` — list, add, update, delete
- `DeviceRepository` — registerDevice, listDevices, revoke
- `OtpRepository` — request, verify

### Stubbed feature paths (verified)
| Feature | Stub location | Replaced by |
|---|---|---|
| Nearby users grid | [feature-user/.../UserFeature.kt:152-162](../feature-user/src/main/kotlin/com/amanah/feature/user/mvi/UserFeature.kt#L152-L162) | hard-coded `Aisha`, `Omar` |
| Admin user list | [feature-admin/.../AdminFeature.kt:81-91](../feature-admin/src/main/kotlin/com/amanah/feature/admin/mvi/AdminFeature.kt#L81-L91) | hard-coded 2 users |
| Admin alerts | [feature-admin/.../AdminFeature.kt:88-91](../feature-admin/src/main/kotlin/com/amanah/feature/admin/mvi/AdminFeature.kt#L88-L91) | hard-coded 1 alert |
| Admin approve / suspend | [feature-admin/.../AdminFeature.kt:99-104](../feature-admin/src/main/kotlin/com/amanah/feature/admin/mvi/AdminFeature.kt#L99-L104) | MVI-local mutation only |
| Incident detail (user) | [feature-user/.../incidentdetail/IncidentDetailInteractor.kt](../feature-user/src/main/kotlin/com/amanah/feature/user/node/incidentdetail/IncidentDetailInteractor.kt) | fabricated fixture with timeline |
| Alert detail (admin) | [feature-admin/.../alertdetail/AdminAlertDetailInteractor.kt](../feature-admin/src/main/kotlin/com/amanah/feature/admin/node/alertdetail/AdminAlertDetailInteractor.kt) | fabricated victim/responder data |
| User detail (admin) | [feature-admin/.../userdetail/AdminUserDetailInteractor.kt](../feature-admin/src/main/kotlin/com/amanah/feature/admin/node/userdetail/AdminUserDetailInteractor.kt) | fabricated identity, devices, activity |

---

## 6. Realtime Persistence Findings

### Outbound (client → server)
- Client gateway sends `emergency.alert` envelope over WSS.
- Backend `websocket_v2._handle_emergency_alert` is a TODO (logs only).
- **Net effect:** the outbound emergency-alert path is **lossy**. No row is ever written.

### Inbound (server → client)
- Server can broadcast `responder.location` and `emergency.alert` envelopes to subscribers via `ConnectionManager.broadcast_*`.
- These broadcasts originate from REST endpoints (e.g. `POST /incidents/{id}/location` does both the DB write and a WS broadcast).
- **Net effect:** for inbound to work end-to-end, all SOS triggers must come through REST. WS-triggered SOS does not propagate.

### Acknowledgements
- The client-side `AckRegistry` expects `ack` envelopes for every sent envelope.
- The backend (`websocket_v2.py`) does send `ack` envelopes, but they are transport-only — no `incident_events.ACK_RECEIVED` row.

### Outbound queue durability
- `OutboundQueue` (client) holds undelivered envelopes in memory.
- Killing the app process loses any queued SOS. **This is the single most critical reliability gap.**

---

## 7. Missing Infrastructure

Things needed for end-to-end operation that currently *do not exist*:

1. **Android repositories** for every feature except auth.
2. **Android offline cache** (Room or DataStore-Proto) for nearby users, alert history, profile, trusted contacts.
3. **Durable outbound queue** — DataStore-Proto-backed so SOS in airplane mode survives process death.
4. **Backend WebSocket persistence** — `_handle_emergency_alert` and `_handle_responder_location` must call services that persist to DB. Or (preferred) deprecate WS for emergency-trigger and have the client always POST /incidents/sos and use WS only for inbound fanout.
5. **Backend `/api/v1/users/nearby`** — endpoint + repository method + (probably) PostGIS spatial query keyed by H3 cell.
6. **Backend duplicate-event protection** — WS handlers should dedupe by client-supplied `event_id` so a network-flap-induced replay doesn't double-fire a notification.
7. **Backend health check** that pings the DB (`/health` currently does not validate the DB connection).
8. **`backend/.env.example`** committed so a fresh checkout can `docker-compose up` without guessing.
9. **CI** that runs `alembic upgrade head` against a disposable Postgres and runs the backend test suite.

---

## 8. Fake / Mocked Components Found

The exhaustive list (Android only — backend has no fakes):

| Path | Type | Replacement |
|---|---|---|
| `feature-user/.../UserFeature.kt:152-162` | hard-coded nearby list | `UserRepository.listNearbyActiveUsers()` |
| `feature-admin/.../AdminFeature.kt:81-94` | hard-coded user list + alert | `AdminRepository.listUsers()` + `AdminRepository.listAlerts()` |
| `feature-admin/.../AdminFeature.kt:99-110` | local mutations on approve/suspend/resolve | `AdminRepository.approveUser/suspendUser/resolveIncident()` |
| `feature-user/.../incidentdetail/IncidentDetailInteractor.kt` | fabricated incident fixture | `EmergencyRepository.getIncident(alertId)` |
| `feature-admin/.../alertdetail/AdminAlertDetailInteractor.kt` | fabricated alert + responders | `AdminRepository.getAlert(alertId)` + WS subscribe |
| `feature-admin/.../userdetail/AdminUserDetailInteractor.kt` | fabricated user / devices / activity | `AdminRepository.getUser(id)` + `DeviceRepository.list(userId)` + `AuditLogRepository.recent(userId)` |
| `feature-user/.../UserDashboardInteractor.kt:107` (`val userH3Cell = "872bedfd5ffffff"`) | hard-coded H3 cell | `LocationProvider.currentH3Cell()` |
| `backend/app/websocket_v2.py:_handle_emergency_alert` | TODO | call `IncidentService.create_sos` with the JWT-derived user_id |
| `backend/app/websocket_v2.py:_handle_presence` | log-only | call `UserRepository.update_presence(...)` |

---

## 9. Security Risks (database-layer)

The hardening pass already covered transport and token storage; these are DB-layer specific.

| Risk | Severity | Mitigation |
|---|---|---|
| WS path bypasses audit log | **HIGH** — incidents triggered over WS leave no forensic trace | Force WS handlers to persist via `IncidentService.create_sos` (which writes `audit_logs` alongside) |
| `database_url` defaults include credentials in plain text in `config.py` | MED | Production must override via env / secret manager; `.env.example` should document this |
| `jwt_secret_key` default is `CHANGE-ME-IN-PRODUCTION-USE-VAULT` | HIGH | A release deploy with the default is a P0; CI must reject it |
| `encryption_key` default `CHANGE-ME-32-BYTE-KEY-FOR-AES256` (32 chars exactly) is the field-encryption AES key for PII | HIGH | Same — CI gate |
| `RefreshTokenRepository` writes refresh tokens *unhashed* (need to verify) | MED | Hash refresh tokens at rest with HMAC-SHA-256 so a DB dump doesn't yield session resumption keys |
| No row-level security on multi-tenant tables | MED | Postgres RLS by `organization_id` is the right long-term answer; for now, every repository method must filter on the tenant scope (currently OK per inspection but not enforced by the DB) |
| Audit log writes can fail silently if `audit_repo.log_action` raises after the parent transaction commits | LOW | Wrap audit writes in the same transaction as the parent mutation (already done in `IncidentService.create_sos`); add a test that simulates audit failure |

---

## 10. Database Integration Gap Analysis

Mapping each gap to its blast radius:

| Gap | Blast radius |
|---|---|
| Android features stubbed | Demo only shows fake data; real users see nothing of their own state |
| No client repositories | Cannot wire any feature to backend without writing them first |
| WS emergency path not persisted | Forensic / audit / replay-protection black hole for SOS |
| OutboundQueue ephemeral | Triggering SOS in airplane mode then losing process = silent failure of a safety event |
| No offline cache | App is unusable offline; alert history requires connection |
| Missing `/users/nearby` endpoint | Backend cannot serve the Home tab's nearby grid |
| Missing health check | Operators cannot detect a degraded DB before user impact |
| Missing CI migration check | Future migration breaks ship without notice |

---

## 11. Where to start (one-line answer)

> **Write the Android client repositories (User, Admin, Emergency, Notifications) and switch the SOS path from WS-only to REST + WS.**

Two engineer-weeks. Tracked file-by-file in [DATABASE_IMPLEMENTATION_STEPS.md](DATABASE_IMPLEMENTATION_STEPS.md). Validation harness in [END_TO_END_CONNECTION_CHECKLIST.md](END_TO_END_CONNECTION_CHECKLIST.md).

---

## 12. Companion documents

- [POSTGRESQL_INTEGRATION_PLAN.md](POSTGRESQL_INTEGRATION_PLAN.md) — DB-level work needed on backend (one new endpoint, hardened health-check, etc.).
- [API_DATABASE_WIRING_STATUS.md](API_DATABASE_WIRING_STATUS.md) — per-endpoint persistence inventory.
- [ANDROID_BACKEND_CONNECTION_STATUS.md](ANDROID_BACKEND_CONNECTION_STATUS.md) — per-feature client-side wiring inventory.
- [REALTIME_PERSISTENCE_STATUS.md](REALTIME_PERSISTENCE_STATUS.md) — WS-channel persistence gaps + ack-protocol storage strategy.
- [DATABASE_IMPLEMENTATION_STEPS.md](DATABASE_IMPLEMENTATION_STEPS.md) — exact file-by-file implementation plan + order.
- [END_TO_END_CONNECTION_CHECKLIST.md](END_TO_END_CONNECTION_CHECKLIST.md) — verification harness for "is it actually connected?".
