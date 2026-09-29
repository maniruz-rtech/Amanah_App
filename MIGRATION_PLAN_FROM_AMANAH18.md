# Migration Plan — amanah18 → Amanah_App

What to **port**, what to **adapt**, what to **leave behind** as we move from the legacy `/home/mzaman/amanah18` codebase to the active `/home/mzaman/Amanah_App` Bazel/Kotlin project.

The fastest credible path to a working Amanah is **NOT** to rewrite the backend or admin in Kotlin. It is to:

1. **Adopt the existing FastAPI backend** as-is, alongside the new Android client.
2. **Adopt the existing Alembic schema** as-is.
3. **Use the Flutter app as a UX reference**, not as code to port literally.
4. **Replace the React admin** in Phase 2 with the native Android admin already scaffolded in `feature-admin`.

This document is the migration manifest for that strategy.

---

## 1. Migration Strategy Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       amanah18 (legacy)                          │
│                                                                  │
│   ┌─────────────┐     ┌───────────────┐     ┌───────────────┐    │
│   │  Flutter    │     │  React Admin  │     │   FastAPI     │    │
│   │   ~28K LOC  │     │   ~15K LOC    │     │   ~17K LOC    │    │
│   │             │     │               │     │               │    │
│   │  REFERENCE  │     │   REPLACE     │     │    ADOPT      │    │
│   │  UX & API   │     │   with Kotlin │     │   AS-IS       │    │
│   │  contracts  │     │   feature-admin│     │  (this is the │    │
│   │             │     │               │     │   shortcut)   │    │
│   └─────────────┘     └───────────────┘     └───────────────┘    │
│         │                    │                      │            │
└─────────│────────────────────│──────────────────────│────────────┘
          │                    │                      │
          ▼                    ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Amanah_App (active)                         │
│                                                                  │
│        ┌────────────────────────────────────┐                    │
│        │      Native Android (Kotlin)       │                    │
│        │   feature-auth, feature-user,      │                    │
│        │   feature-admin, feature-emergency │                    │
│        │   feature-core                     │                    │
│        └────────────────────────────────────┘                    │
│                         │                                        │
│                    HTTPS + WSS                                   │
│                         │                                        │
│        ┌────────────────────────────────────┐                    │
│        │   backend/  (vendored FastAPI)     │ ← from amanah18    │
│        │   alembic/  (existing migrations)  │ ← from amanah18    │
│        └────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. What to Port (high ROI)

### 2.1 Backend — port entirely

Effort: **1.0 day** (mostly redeploy + repackage).

| amanah18 path | target | notes |
|---|---|---|
| `/home/mzaman/amanah18/backend/app/` | `Amanah_App/backend/app/` | Vendor or submodule; no code changes needed |
| `/home/mzaman/amanah18/backend/alembic/` | `Amanah_App/backend/alembic/` | Keep migration history intact |
| Backend setup scripts (`setup-dev.sh`, `start-system.sh`, `stop-system.sh`) | `Amanah_App/scripts/backend/` | Refactor paths only |

**Subsystems to keep:**
- All Pydantic schemas (`app/schemas/`)
- All SQLAlchemy models (`app/db/models/`)
- All API routers (`app/api/v1/`)
- All services (`app/services/`)
- All repositories (`app/repositories/`)
- WebSocket `ConnectionManager` (`app/websocket.py`)
- Encryption + JWT (`app/core/security.py`)
- Permissions (`app/core/permissions.py`, `app/core/admin_permissions.py`)
- Celery workers (`app/workers/`, `app/tasks/`)
- Settings (`app/core/config.py`)
- Logging (`app/core/logging.py`)
- All exception classes (`app/core/exceptions.py`) — the Kotlin client error handling will map onto these
- Test harness (`backend/tests/`)

**Small adaptations needed:**
- Confirm CORS origins allow the new Android app (use `https://app.amanah.example` for production; allow `http://localhost:*` for development).
- Verify `JWT_SECRET` rotation policy.
- Ensure `MAPS_API_KEY` for the *server-side* Maps usage (if any) is separate from the client's.
- Move secrets out of `.env` to KMS/Vault for production.

### 2.2 Database schema — keep verbatim

The Postgres schema is already production-quality:
- 18 tables with proper relationships, soft-delete, audit columns.
- ULID-based IDs with type prefixes (`usr_`, `inc_`, etc.).
- Encrypted-at-rest PII columns (`*_encrypted` + `*_hash`).
- Proper indices on every foreign-key + frequent-query column.
- Multi-tenancy via `organization_id` + `region_id`.

**Action:** `pg_dump` the schema (no data) from a current dev DB and apply via `alembic upgrade head` on the new project's database. Seed admin user + demo organisation + demo region via a new `alembic` data migration.

### 2.3 API contracts — keep verbatim

Endpoints to consume from the Kotlin client (in priority order for demo):

| Endpoint | Used by | Kotlin caller |
|---|---|---|
| `POST /api/v1/auth/login` | LoginFeature | `AuthRepository.login(...)` |
| `POST /api/v1/auth/refresh` | RefreshInterceptor | `AuthRepository.refresh(...)` |
| `POST /api/v1/auth/logout` | logout button | `AuthRepository.logout()` |
| `GET  /api/v1/users/me` | UserDashboard / Profile | `UserRepository.getMe()` |
| `PATCH /api/v1/users/me` | edit profile | `UserRepository.updateMe(...)` |
| `POST /api/v1/users/devices` | FCM token registration | `DeviceRepository.register(...)` |
| `GET  /api/v1/users/trusted-contacts` | trusted contacts list | `TrustedContactsRepository.list()` |
| `POST /api/v1/users/trusted-contacts` | add | `.add(...)` |
| `PATCH /api/v1/users/trusted-contacts/{id}` | edit | `.update(...)` |
| `DELETE /api/v1/users/trusted-contacts/{id}` | delete | `.delete(...)` |
| `POST /api/v1/incidents/sos` | EmergencyButton | `EmergencyRepository.createSos(...)` |
| `POST /api/v1/incidents/{id}/location` | live location updates | `EmergencyRepository.pushLocation(...)` |
| `POST /api/v1/incidents/{id}/cancel` | cancel emergency | `EmergencyRepository.cancel(...)` |
| `POST /api/v1/incidents/{id}/resolve` | admin force-resolve | `AdminRepository.resolveIncident(...)` |
| `GET  /api/v1/incidents/{id}` | incident detail | `EmergencyRepository.get(...)` |
| `GET  /api/v1/incidents/my/active` | active alerts list | `EmergencyRepository.listMyActive()` |
| `GET  /api/v1/notifications` | notification center | `NotificationsRepository.list()` |
| `POST /api/v1/notifications/mark-read` | mark read | `.markRead(...)` |
| `POST /api/v1/notifications/mark-all-read` | mark all read | `.markAllRead()` |
| `GET  /api/v1/notifications/unread-count` | badge | `.unreadCount()` |
| `POST /api/v1/otp/request` | OTP for phone/email verify | `OtpRepository.request(...)` |
| `POST /api/v1/otp/verify` | OTP verify | `OtpRepository.verify(...)` |
| `POST /api/v1/auth/password-reset/request` | password reset | `AuthRepository.requestPasswordReset(...)` |
| `GET  /api/v1/admin/users` | admin user list | `AdminRepository.listUsers()` |
| `GET  /api/v1/admin/users/{id}` | admin user detail | `AdminRepository.getUser(...)` |
| `POST /api/v1/admin/approvals/{id}/approve` | approve user | `AdminRepository.approveUser(...)` |
| `POST /api/v1/admin/users/{id}/suspend` | suspend user | `AdminRepository.suspendUser(...)` |
| `GET  /api/v1/admin/audit-logs` | audit log viewer | `AdminRepository.listAuditLogs(...)` |
| WS `/ws?token=...` | live updates | `AmanahWebSocketService.observe*()` |

### 2.4 WebSocket protocol — adapt the wire format

amanah18 sends messages as:
```json
{ "type": "location_update", "payload": { "incident_id": "...", "lat": ..., "lng": ..., "accuracy_m": ... } }
```

The Kotlin Scarlet service expects flat fields like `EmergencyAlertWireMessage` with `alertId`, `victimId`, `lat`, `lng`, `h3Cell`, `status`, `kRing`, `timestamp`.

**Action:** Either (a) add a server-side adapter that emits messages in the new flat-shape format keyed by `type` discriminator, OR (b) write a Scarlet message adapter that unpacks `{type, payload}` into the appropriate `WireMessage`. **Recommended: option (b)** — keep server backward-compatible with the Flutter app during transition.

Effort: 0.5 day.

### 2.5 Flutter screen catalogue — use as UX reference

Do **NOT** port Flutter code. Use the screen list as the requirements document for Compose screens.

Reference screens worth mining for UX patterns:

| Flutter screen | Reuse for | Kotlin target |
|---|---|---|
| `app_shell/widgets/app_drawer.dart` | Side drawer pattern | (later) `feature-core/ui/AmanahDrawer.kt` |
| `app_shell/widgets/app_bottom_navigation.dart` | Bottom nav role-based | already implemented |
| `app_shell/widgets/role_based_navigation.dart` | Role gating | session-driven router |
| `sos/screens/quick_sos_screen.dart` | One-tap SOS UX | already in `UserDashboardView` |
| `sos/screens/detailed_sos_screen.dart` | Type + severity + note | NEW screen (`DetailedSosNode`) |
| `sos/widgets/incident_type_selector.dart` | Type picker | NEW Compose `IncidentTypeSelector` |
| `sos/widgets/severity_selector.dart` | Severity picker | NEW |
| `sos/widgets/location_picker.dart` | Manual location pin drop | NEW |
| `sos/widgets/incident_status_badge.dart` | Status pill | NEW `AmanahStatusBadge` |
| `responder_incident_detail/screens/responder_incident_detail_screen.dart` | Responder POV detail | NEW (P1) |
| `dispatcher_dashboard/` | Operator dashboard | NEW (admin-side, P1) |
| `live_incident_status/screens/incident_live_status_screen.dart` | Live updates feed | becomes part of incident detail |
| `nearby_incidents/screens/nearby_incidents_screen.dart` | Map of nearby incidents | NEW `NearbyIncidentsNode` |
| `notifications/` | Notification center | NEW |
| `profile/` | Profile screens | NEW (port layouts) |
| `trusted_contacts/` | Trusted contacts | NEW (P1) |
| `password_reset/` | Reset flow | partially in `PasswordResetView` |
| `otp/` | OTP code entry | NEW `OtpEntryComponent` |
| `device/` | Device info card | NEW |
| `settings/` | Settings screens | NEW (P1) |

### 2.6 React admin screen catalogue — kill and replace

Do **NOT** port React. The Kotlin `feature-admin` will absorb each page natively:

| React page | Kotlin equivalent | Status |
|---|---|---|
| `LoginPage.tsx` | shared `LoginNode` | ✅ scaffolded |
| `DashboardPage.tsx` | `AdminDashboardNode` | 🟡 scaffolded; needs real data |
| `ApprovalsPage.tsx` | `AdminApprovalsNode` | ❌ new |
| `AuditLogsPage.tsx` | `AdminAuditLogNode` | ❌ new |
| `IncidentListPage.tsx` | `AdminDashboardView.AlertsTab` | 🟡 |
| `IncidentDetailsPage.tsx` | `AdminAlertDetailNode` | ❌ new |
| `NotificationCenterPage.tsx` | shared with user-side | ❌ new |
| `OrganizationListPage.tsx` | `AdminOrganisationsNode` | ❌ new |
| `RegionListPage.tsx` | `AdminRegionsNode` | ❌ new |
| `RoleListPage.tsx`, `RoleDetailsPage.tsx` | `AdminRolesNode` | ❌ new |
| `SettingsPage.tsx` | `AdminSettingsNode` | ❌ new |
| `UserCreatePage.tsx`, `UserDetailsPage.tsx`, `UserListPage.tsx` | `feature-admin` user nodes | 🟡 list scaffolded; detail/create new |

**Cost decision:** Keeping the React admin in parallel is acceptable for Phase 1 (saves engineering hours), but the native admin must be the long-term home (consistent auth, no separate deployment, mobile-first).

### 2.7 Assets

| amanah18 path | target | notes |
|---|---|---|
| `assets/icons/` | `app/src/main/res/drawable/` (vectors) and `app/src/main/res/mipmap-*` (launcher) | convert PNGs to vectors where possible |
| `assets/images/` | `app/src/main/res/drawable/` or `feature-core/src/main/res/drawable/` | brand images |
| `assets/fonts/` | `feature-core/src/main/res/font/` | already partially set up (Type.kt references FontRes) |
| `flutter_app/assets/icons/`, `flutter_app/assets/images/` | merge into above | likely duplicates |

---

## 3. What to Adapt (medium effort)

### 3.1 Auth contract shape

amanah18 returns `LoginResponse` with `access_token`, `refresh_token`, `token_type`, `expires_in`, `user`, and `mfa_required` flag. The Kotlin client currently doesn't model this. Add `AuthDtoMapper` to translate to `AuthenticatedUser` (Kotlin) and stash tokens in `TokenStore`.

Effort: 0.5 d.

### 3.2 Incident status alignment

amanah18 `IncidentStatus` is `BROADCASTING / ASSIGNED / IN_PROGRESS / RESOLVED / CANCELLED`. Kotlin `EmergencyState.Phase` is `IDLE / BROADCASTING / CALCULATING_ETA / VICTIM_LOCATED / RESPONDER_EN_ROUTE / ACTIVE_EMERGENCY` (the last being a wire-compat alias).

**Action:** Keep the Kotlin phases as the *client UI state machine* (richer than the server's status). Map server `IncidentStatus` → Kotlin `Phase` via a converter:
- `BROADCASTING` → `BROADCASTING` or `CALCULATING_ETA` (depending on whether ETAs have arrived)
- `ASSIGNED` → `VICTIM_LOCATED`
- `IN_PROGRESS` → `RESPONDER_EN_ROUTE`
- `RESOLVED` → `IDLE` (then dismiss UI)
- `CANCELLED` → `IDLE` (then dismiss UI)

Effort: 0.5 d.

### 3.3 H3 cell on server

Server doesn't currently store `h3_cell` on incidents — the new client expects it for the proximity-broadcast model.

**Action:** Add `h3_cell` (resolution 7) and `h3_cell_block` (resolution 9) columns to `incidents` and `emergency_locations`. Compute server-side via the `h3-py` library. Add Alembic migration.

Effort: 1.0 d.

### 3.4 Responder location broadcast

Server's WebSocket emits per-incident location broadcasts via `incident_subscriptions`. The new client expects `observeResponderLocations()` to be filtered by *the responder's own pending alerts* (push-style).

**Action:** Add a `responder_alert_pool` table or Redis set keyed by user_id; server picks the right subscribers when broadcasting responder location updates.

Effort: 1.0 d.

### 3.5 Roles

amanah18 has rich role taxonomy: `super_admin`, `regional_admin`, `responder`, regular user (no explicit "USER" role string). Kotlin has only `UserRole.ADMIN / USER`.

**Action:** Extend Kotlin `UserRole` to mirror server: `SUPER_ADMIN`, `REGIONAL_ADMIN`, `RESPONDER`, `MEMBER`. Update `RootNode` to branch into 3 dashboards (admin / responder / member) — OR collapse into 2 (admin / non-admin) for MVP. **Recommend: 3 dashboards once responder workflows are real (Week 2-3); 2 dashboards for the demo.**

Effort: 0.5 d initial; 1.5 d if responder dashboard ships.

### 3.6 Org + region awareness

amanah18 is strictly multi-tenant. Every list endpoint filters by `organization_id` + `region_id`. The new Kotlin client doesn't carry these.

**Action:** Extend `AuthenticatedUser` (Kotlin) to include `organizationId` + `regionId`. Carry into every API call where relevant. For the MVP demo with a single org, this is straightforward.

Effort: 0.5 d.

---

## 4. What NOT to Migrate

### 4.1 Flutter app code
- Different language, different framework, different state-management style.
- Porting Riverpod providers to MVICore is a lateral effort with no architectural gain.
- The Compose UI for the new project is already higher-fidelity for the screens that exist.
- **Use Flutter only as a UX reference (screenshots, flows, copy).**

### 4.2 React admin code
- Already covered in §2.6. Replace, don't port.

### 4.3 Firebase config
- `firebase_options.dart` is generated for the *Flutter* package name. The new app's `applicationId` is `com.amanah.app` (per `BUILD.bazel:34-39`).
- Re-issue: `google-services.json` for Android, including SHA-1 fingerprints for debug + release signing.

### 4.4 Build artifacts
- `backend/.venv/`, `backend/venv/`, `flutter_app/build/`, `flutter_app/.dart_tool/`, `admin-panel/node_modules/` — local-only, do not vendor.

### 4.5 Setup scripts that assume Flutter / React presence
- `start-system.sh`, `stop-system.sh`, `setup-dev.sh` reference all three projects. Rewrite for the new layout.

### 4.6 Documentation that documents the old structure
- `README.md`, `README2.md`, `SETUP_LOCAL.md`, `START_SERVICES.md` — read for reference, then write fresh docs in `Amanah_App/`.

### 4.7 `ADMIN_PANEL_IMPLEMENTATION_PLAN.md`
- 41K of React admin planning. Mine for UX requirements, then archive.

---

## 5. Migration Phasing

### Phase 0 — Setup (day 1)
- Vendor amanah18 backend into `Amanah_App/backend/` (either submodule or copy).
- Vendor amanah18 alembic into `Amanah_App/backend/alembic/`.
- Create `docker-compose.yml` at the project root for: postgres+postgis, redis, fastapi, celery worker, celery beat.
- Run `alembic upgrade head` against a fresh Postgres instance.
- Seed: 1 organisation, 1 region, 1 super-admin, 3 demo users.

### Phase 1 — Wire client to backend (days 2-5)
- Day 2: DI graph, ApiService, OkHttp client, AuthInterceptor, RefreshInterceptor.
- Day 3: AuthRepository wired into LoginFeature. Token persistence.
- Day 4: WebSocket factory wired. AmanahWebSocketService injected. Subscribe-on-login flow.
- Day 5: EmergencyAlertEngine `wsPublish` wired. Test end-to-end SOS round-trip.

### Phase 2 — Backfill missing user flows (week 2)
- DetailedSosNode (with type + severity + note).
- TrustedContactsNode (port from Flutter).
- ProfileNode (edit + verify phone/email).
- NotificationCenterNode.
- Background EmergencyForegroundService.
- FCM device token registration.

### Phase 3 — Backfill admin (week 3-4)
- AdminUserDetailNode (replaces React `UserDetailsPage`).
- AdminApprovalsNode (replaces React `ApprovalsPage`).
- AdminAlertDetailNode (replaces React `IncidentDetailsPage`).
- AdminAuditLogNode.
- AdminOrganisationsNode / RegionsNode / RolesNode.
- Switch from React admin to native admin (kill the React deployment).

### Phase 4 — Adapter cleanup (week 5)
- Remove WebSocket `{type, payload}` adapter once Flutter is decommissioned.
- Remove any temporary `LegacyDto` mappers.
- Remove the entire React admin deployment.

### Phase 5 — Decommission amanah18 (month 2)
- Mark amanah18 repo read-only.
- Archive `flutter_app/`.
- Archive `admin-panel/`.
- The backend remains the same code; it just now lives at `Amanah_App/backend/`.

---

## 6. Migration Risks

| Risk | Mitigation |
|---|---|
| Backend's WebSocket connection-manager is in-memory; doesn't scale to multiple instances. | Phase 2: Redis pub/sub. (Already in [TECHNICAL_DEBT_REPORT.md §D1](TECHNICAL_DEBT_REPORT.md).) |
| Re-issuing Firebase config could disrupt existing test users (if any). | Use a *new* Firebase project for the new app; keep the old one alive while Flutter is still around. |
| Schema additions (h3_cell columns) on production DBs require a deploy gate. | Run as separate Alembic revision; deploy backend first, then client. |
| API breaking changes during transition will break the Flutter app. | Add new endpoints alongside old; deprecate after Flutter is killed. Or use a versioned API (`/api/v2/...`). |
| Demo seed data leaks to production. | Seed only against `ENVIRONMENT=development`; the `app/core/config.py` already has this guard — use it. |
| Encryption key rotation between old/new deployments. | Use the same `JWT_SECRET` + PII encryption key in both deployments during transition. Plan a key-rotation runbook for after. |
| `MAPS_API_KEY` confusion (web vs. Android keys). | Issue separate Maps Platform API keys for: web admin, Android app, server geocoding. Restrict by referrer / package. |

---

## 7. Migration Checklist

```
[ ] Backend
    [ ] Copy backend/app → Amanah_App/backend/app
    [ ] Copy backend/alembic → Amanah_App/backend/alembic
    [ ] Write docker-compose.yml (postgres+postgis, redis, fastapi, celery)
    [ ] alembic upgrade head on fresh dev DB
    [ ] Seed demo org + region + admin + 3 users
    [ ] Verify `curl http://localhost:8000/api/v1/health`
    [ ] Verify `wscat -c "ws://localhost:8000/ws?token=<token>"`
    [ ] Add Redis pub/sub adapter (deferred to Phase 2)

[ ] Schema additions
    [ ] Alembic migration: add `h3_cell` (varchar(16)) to incidents
    [ ] Alembic migration: add `h3_cell_block` (varchar(16)) to incidents
    [ ] Alembic migration: add `h3_cell` to emergency_locations
    [ ] Add server-side h3-py library to compute cells on insert

[ ] Client (Kotlin)
    [ ] Build AppComponent (Dagger)
    [ ] Build ApiService (Retrofit)
    [ ] Build AuthInterceptor + RefreshInterceptor
    [ ] Build TokenStore (DataStore + Tink)
    [ ] Build SessionManager
    [ ] Build AmanahWebSocketService factory (ScarletFactory)
    [ ] Build WireMessage adapter for {type, payload} envelope
    [ ] Wire LoginFeature.authenticate → AuthRepository.login
    [ ] Wire EmergencyAlertEngine.wsPublish → ws.publishEmergencyAlert
    [ ] Wire UserDashboardInteractor → ws.observeEmergencyAlerts → engine.onIncomingAlert
    [ ] Wire admin AdminFeature.LoadAll → AdminRepository.listUsers + listAlerts

[ ] Kill list (delete from Amanah_App)
    [ ] app/.../node/AppNode.kt (dead root)
    [ ] feature-core/.../node/dashboard/ (Islamic-modules dashboard)
    [ ] feature-core/.../mvi/DashboardFeature.kt (Islamic modules)
    [ ] feature-core/.../geo/H3LocationIndex.kt (duplicate)
    [ ] All hard-coded sample names ("Aisha", "Omar") behind BuildConfig.DEBUG

[ ] Assets
    [ ] Reissue Firebase google-services.json for com.amanah.app
    [ ] Re-license / re-issue Google Maps API key for Android with package + SHA-1 restriction
    [ ] Migrate brand assets (icons, images, fonts) from amanah18/assets/ to feature-core/res/

[ ] Documentation
    [ ] Write Amanah_App/README.md
    [ ] Write Amanah_App/CONTRIBUTING.md
    [ ] Write Amanah_App/SECURITY.md
    [ ] Archive amanah18/README*.md, ADMIN_PANEL_IMPLEMENTATION_PLAN.md (move to docs/archive/)

[ ] Demo
    [ ] Demo seed script (3 users, 1 pending approval, fake-responder dispatcher)
    [ ] Test full demo flow end-to-end
    [ ] Cut release-candidate-demo-1 tag

[ ] Decommission (after MVP)
    [ ] Mark amanah18 read-only
    [ ] Archive flutter_app/ and admin-panel/
    [ ] Remove legacy {type,payload} WS adapter on backend
```

---

## 8. Migration Effort Roll-up

```
Phase 0 (backend setup)                              :  1 d
Phase 1 (client wiring)                              :  5 d
Phase 2 (user-flow backfill)                         : 12 d
Phase 3 (admin backfill + React decommission)        : 14 d
Phase 4 (adapter cleanup)                            :  3 d
Phase 5 (legacy decommission, archive)               :  1 d
                                                       ─────
                                              TOTAL  : 36 d
```

With 2 engineers in parallel, **~18 working days** (≈3.5 weeks) end-to-end. Phase 0 + 1 alone (≈3 working days at 2 engineers) gets the customer demo.

---

## 9. Outcomes Summary

After migration:
- ✅ Native Android client (the goal)
- ✅ Existing FastAPI backend reused (no rewrite cost)
- ✅ Existing schema + migrations preserved (no data-loss risk)
- ✅ Existing audit trail preserved
- ✅ Single-codebase admin (no separate React deployment)
- ✅ Privacy-first H3 indexing (improvement over amanah18's radius approach)
- ✅ Cleaner MVI architecture than Flutter's Riverpod model
- ⚠️ Flutter app retired (was never in production)
- ⚠️ React admin retired (replaced by `feature-admin`)
- 🚀 Path to production unlocked
