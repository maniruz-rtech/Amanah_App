# Amanah_App — Project Audit & Continuation Roadmap

**Audit date:** 2026-05-21
**Auditor scope:** Principal-engineer audit of `/home/mzaman/Amanah_App` (active) vs. `/home/mzaman/amanah18` (reference legacy).
**Bottom line:** Amanah_App is an *architectural skeleton* (≈5.6K LOC of Kotlin). amanah18 is a *working multi-tenant emergency platform* (≈61K LOC across FastAPI + Flutter + React admin). There is currently **no backend, no real data layer, no DI graph, and no customer-demo-ready UI flow** in the active project. This document is the punch list to fix that.

---

## 1. Executive Summary

### What Amanah_App is today
A Bazel/Kotlin-only Android project using:
- **Bazel 8** + `rules_kotlin` 2.1 + `rules_android` 0.6 + Kotlin 2.1
- **Jetpack Compose** (Material 3) for UI
- **Badoo MVICore 2.x** + **Reaktive 2.x** + a small *in-house "Nodes" framework* (`libraries/nodes-framework`) that imitates Badoo's RIBs/Nodes
- **Scarlet** for WebSocket
- **Uber H3** for geospatial cell indexing
- **Google Maps Compose**, **Retrofit/OkHttp**, **Dagger**, **AndroidX Security-Crypto**, **kotlinx-coroutines/serialization**

The architecture is **production-grade in design** (clean MVI, privacy-aware H3 indexing, k-ring proximity matching, Box-Muller location obfuscation, lifecycle-safe `autoDispose`). It is **not production-grade in execution**: nearly every data-fetch is stubbed, no backend client exists, and there is no customer-visible end-to-end flow.

### What amanah18 is
A complete (though not yet shipped) emergency-response platform:
- **FastAPI** backend (~17K LOC) — JWT+MFA auth, Argon2id, encrypted PII, PostgreSQL+PostGIS, Redis+Celery, comprehensive WebSocket connection manager, request tracing, structured logging, repository/service pattern.
- **Flutter** app (~28K LOC) — 18 presentation modules: app_shell, dashboard, dispatcher_dashboard, SOS (quick + detailed), live_incident_status, live_tracking, location_tracking, nearby_incidents, responder_incident_detail / actions / availability, profile (with verify_phone/verify_email), trusted_contacts, notifications, OTP, password_reset, settings, device.
- **React admin panel** (~15K LOC, Vite + Tailwind, 15 pages) — Login, Dashboard, Approvals, AuditLogs, Incident/Org/Region/Role/User lists & details, NotificationCenter, Settings.

### Recommendation, one paragraph
Stop treating amanah18 as throwaway. The new Android skeleton is well-architected but lacks 80% of the platform machinery. The fastest path to a *customer-demoable* Amanah is: **(a)** stand the amanah18 FastAPI backend back up under the new domain (it already implements the contracts the new Android client expects); **(b)** delete the dead "Islamic dashboard" subtree from Amanah_App; **(c)** wire the existing Login/User/Admin nodes to that backend via Retrofit+Scarlet; **(d)** finish three missing critical screens (Onboarding, Trusted Contacts, Incident Detail) and you have a demo. Everything else is polish.

---

## 2. Tech Stack Detection

### Amanah_App (active)

| Layer | Tech | Status |
|---|---|---|
| Build | Bazel 8 + rules_kotlin + rules_jvm_external | ✅ wired, builds defined |
| Language | Kotlin 2.1.0 | ✅ |
| UI | Jetpack Compose + Material 3 + Compose Maps | ✅ deps; ~6 screens partial |
| Arch (presentation) | Custom Nodes framework + MVICore 2.x + Reaktive 2.x | ✅ skeleton; idiomatic |
| Realtime | Scarlet + Reaktive stream adapter | ⚠️ interface defined, no factory used |
| Geospatial | Uber H3 (`com.uber:h3:4.1.1`) | ✅ wrapped in `H3LocationIndex` |
| Maps | maps-compose 6.2.1 + play-services-maps/-location | ✅ used in `ResponderMapView` |
| Networking | Retrofit 2.11 + OkHttp 4.12 + Gson 2.11 | ❌ deps only; no client built |
| DI | Dagger 2.52 | ❌ deps only; no component graph |
| Storage | AndroidX Security-Crypto (alpha06) | ❌ deps only; no EncryptedSharedPreferences usage |
| Push | (none) | ❌ no Firebase wired |
| Tests | JUnit 4 + kotlin-test + MockK | ❌ zero tests written |
| CI | (script only: `scripts/bazel_diff.sh`) | ❌ no GitHub Actions / Bitrise |
| Static analysis | NullAway + ErrorProne (kt_compiler_plugin) | ✅ wired into root BUILD |

### amanah18 (legacy)

| Layer | Tech | Status |
|---|---|---|
| Backend | FastAPI + SQLAlchemy 2 async + Pydantic v2 + Alembic | ✅ working |
| DB | PostgreSQL 16 + PostGIS | ⚠️ ran locally |
| Cache/Queue | Redis 7 + Celery | ⚠️ Redis was not installed at last status |
| Auth | JWT (python-jose) + Argon2id + MFA (TOTP) + Encrypted-at-rest PII | ✅ working |
| Realtime | Native FastAPI WebSocket + `ConnectionManager` | ✅ working |
| Observability | structlog + request-ID middleware | ✅ working |
| Mobile | Flutter 3.x + Riverpod + GoRouter + Dio + Hive + FCM | ✅ extensive |
| Admin | React 18 + Vite + Tailwind + React-Hook-Form + Zod | ✅ extensive |

---

## 3. Current Completion Status

**Overall Amanah_App MVP completion: ~12%.**

Breakdown (against an "Amanah-1.0 customer demo" target):

| Area | % done | Notes |
|---|---|---|
| Build system + module layout | 95% | Bazel works, all `BUILD.bazel` present |
| Nodes/MVI framework | 90% | Tiny but coherent |
| Theme + design tokens | 70% | Light/dark palette done; typography incomplete; no spacing/elevation tokens |
| Splash screen | 90% | Real Compose animation; logo is a placeholder Arabic glyph |
| Auth (login UI) | 50% | UI complete; backend call stubbed |
| Auth (password reset) | 25% | UI complete; no backend; no admin flow |
| User dashboard (idle) | 35% | Tabs render; data is stubbed |
| User dashboard (emergency) | 60% | EmergencyFeature + ResponderMapView are real; not wired to WS |
| Admin dashboard | 30% | UI present; CRUD/approvals stubbed |
| WebSocket transport | 20% | Service interface only; Scarlet factory not instantiated |
| Repository layer | 0% | None |
| DI graph | 0% | None |
| Storage (token/session) | 0% | None |
| Push notifications (FCM) | 0% | None |
| Onboarding | 0% | No flow exists |
| Trusted-contacts feature | 0% | Not started (existed in amanah18) |
| Incident detail / history detail | 0% | Only top-level list cards |
| Profile editing / verification | 5% | Read-only Profile tab |
| Settings (real) | 10% | Dark-mode toggle only |
| Tests | 0% | None |
| CI/CD | 5% | One shell script |
| Backend | 0% | Not present in this directory |

---

## 4. Feature Completion Matrix

See companion file: **[FEATURE_COMPLETION_MATRIX.md](FEATURE_COMPLETION_MATRIX.md)** for the per-feature row-by-row matrix.

Top-level summary:
- **22** features were end-to-end functional in amanah18 (backend + Flutter + admin).
- **3** of those have a partial UI in Amanah_App (login, user dashboard scaffold, admin dashboard scaffold).
- **0** have a working data layer in Amanah_App.

---

## 5. UI / UX Readiness Report

See full plan in **[UI_UX_MVP_PLAN.md](UI_UX_MVP_PLAN.md)**.

Headline findings:

1. **There is no customer-demoable UI today.** The login screen, dashboards, and emergency overlay all render, but tapping anything either hits a stub that fails silently or shows hard-coded fake names (`Aisha`, `Omar`).
2. **Two conflicting navigation roots exist in code**:
   - [app/src/main/kotlin/com/amanah/app/node/RootNode.kt](app/src/main/kotlin/com/amanah/app/node/RootNode.kt) — Splash → Login → Admin/User (used by MainActivity).
   - [app/src/main/kotlin/com/amanah/app/node/AppNode.kt](app/src/main/kotlin/com/amanah/app/node/AppNode.kt) — Splash → "Islamic modules dashboard" (Prayer Times, Quran, Zakat, Qibla, Calendar). **This is dead code and contradicts the product identity.** Delete it (see TECHNICAL_DEBT_REPORT.md).
3. **No design system.** Colors and typography are defined; spacing, elevation, motion durations, and component variants are inlined as raw `.dp` literals everywhere. There is no `AmanahSpacing`, `AmanahElevation`, `AmanahMotion`, no reusable `AmanahCard`/`AmanahPrimaryButton`/`AmanahSecondaryButton`/`AmanahErrorBanner` etc.
4. **No reusable components.** Every screen rebuilds its own Scaffold, TopAppBar, Snackbar handling, error state, loading state, and empty state from scratch. amanah18 had `core/widgets/app_loading.dart`, `app_empty.dart`, `app_error.dart` — that pattern should be ported.
5. **No empty / loading / error states for most flows.** Where they exist (Dashboard) they are inline-implemented. The pattern needs to be a 3-state composable that any feature can drop into a `Box`.
6. **No onboarding.** A customer demo should start with branded onboarding (3 screens explaining: trusted community → SOS button → privacy guarantee).
7. **No incident detail screen.** Admin alert list, user alert history, and emergency-active state all need a *drill-down* — currently they don't drill.
8. **No accessibility audit.** No `contentDescription` on the EmergencyButton's animated pulse, no font-scale awareness, no semantic role on the role-based bottom nav.
9. **Map UX is the strongest screen.** `ResponderMapView` is the polished centrepiece — use it as the design reference (haptic-on-press, ETA-coloured markers, WeakHandler camera fly-to, privacy-rounded distance). Other screens are nowhere near that fidelity.

**Customer-demo MVP UI scope (next 7 days):** see Section 10.

---

## 6. Backend Readiness Report

**Amanah_App has no backend in this directory.**

The intent (per `feature-core/websocket/AmanahWebSocketService.kt` and `EmergencyAlertEngine`) is clearly to talk to a Python/FastAPI-style backend with these channels:

- `observeConnectionEvents()` — lifecycle
- `observeEmergencyAlerts()` / `publishEmergencyAlert()` — H3-broadcast to adjacent cells
- `observeResponderLocations()` / `publishResponderLocation()` — exact GPS during ACTIVE_EMERGENCY only
- `publishPresence()` — heartbeat with obfuscated H3 cell
- `observeAdminNotifications()` — approvals / suspensions / system

amanah18's backend already implements **most of this surface** (different naming):
- `POST /api/v1/incidents/sos`, `POST /api/v1/incidents/{id}/location`, `POST /api/v1/incidents/{id}/cancel|resolve`
- `GET /api/v1/responders/...`, status update, accept/decline
- WebSocket `/ws?token=<JWT>` with `subscribe_incident`, `location_update`, `responder_accepted`, `responder_arrived`, `incident_assigned`, `status_update`
- Auth: `/api/v1/auth/login|refresh|logout|mfa/verify|otp/request|otp/verify|password-reset/request|password-reset/complete`
- Users: `/api/v1/users/me`, devices, trusted-contacts
- Admin: approvals, audit logs, organizations, regions, roles, users CRUD
- Notifications: list, mark-read, unread-count

**Recommendation:** *Adopt the amanah18 backend as-is.* Rename/move it under `backend/` of the new repo (or keep it as a sibling repo). The contract mismatch with the Kotlin client is small (mostly renaming `victimLat/Lng` ↔ `lat/lng` and `kRing` semantics).

### Missing production-critical backend systems

| System | Status in amanah18 | What's missing |
|---|---|---|
| Redis | Not installed at last status | Required for Celery, WS pub/sub, rate-limit |
| Celery worker | Pending | Required for FCM dispatch, audit log batching |
| PostGIS | Locally only | Required for spatial queries |
| Migrations | Alembic present | Need to run `alembic upgrade head` on prod |
| Secrets management | Env-only | Need Vault / KMS / sealed secrets |
| Observability backend | structlog only | No Prometheus/Grafana/Loki wired |
| Error tracking | None | Sentry recommended |
| Rate limiting | Exception class exists | Implementation incomplete |
| API versioning | `/api/v1/` prefix | Healthy, no other versions yet |
| OpenAPI spec | Auto from FastAPI | Needs to be locked & committed |
| CORS | Configured via settings | Verify prod origin allowlist |
| WebSocket scaling | Single-process in-memory `ConnectionManager` | Needs Redis pub/sub to go multi-instance |

---

## 7. Reusable Assets From amanah18

See full migration table in **[MIGRATION_PLAN_FROM_AMANAH18.md](MIGRATION_PLAN_FROM_AMANAH18.md)**.

**Migrate (high ROI):**
- The entire `backend/app/` directory (FastAPI). Effort: 1-2 days to redeploy.
- The Alembic migration history.
- All Pydantic schemas (auth, user, incident, responder, OTP, notification, password_reset, trusted_contact, device, admin).
- All SQLAlchemy models (User, Organization, Region, Role/UserRole, Incident, EmergencyLocation, IncidentAssignment, IncidentEvent, Device, TrustedContact, Notification, OTPRequest, PasswordResetRequest, RefreshToken, AdminApproval, AuditLog, ResponderStatus).
- The WebSocket `ConnectionManager` design (port unchanged).
- The Argon2id + JWT + encrypted-PII pattern in `app/core/security.py`.
- The Flutter app's **data layer architecture**: `data/repositories/*` + `data/datasources/*` — the *pattern* maps cleanly to Kotlin repositories/data sources.
- The Flutter app's **screen catalogue** as a UX reference (which screens exist, what they show).

**Don't migrate:**
- The Flutter UI code itself (different framework).
- The React admin panel (the new project's `feature-admin` will absorb its functionality natively).
- `firebase_options.dart` (re-issue Firebase config for the new applicationId `com.amanah.app`).
- Anything under `flutter_app/build/`, `backend/.venv/`, `backend/venv/`.

---

## 8. Critical Missing Systems

Ordered by blocking severity.

1. **No DI graph.** Dagger 2.52 is on the classpath but no `AppComponent` exists. Without DI, every singleton (token store, http client, websocket service, location provider, FCM, repositories) ends up as a global or constructor-injected from arbitrary call sites. This is already starting (see `LoginFeature(authenticate = ...)` default lambda returning `UNKNOWN`).
2. **No HTTP client / Retrofit service.** Dependencies are declared; no `ApiService` interface exists; `OkHttpClient` is not constructed; no auth interceptor; no token refresh interceptor.
3. **No WebSocket factory used.** `ScarletFactory.kt` exists (37 LOC) but `AmanahWebSocketService` is never instantiated by anything. The `EmergencyAlertEngine` accepts a `wsPublish: (EmergencyAlertMessage) -> Unit` callback with a TODO comment.
4. **No persistent storage.** No DataStore, no Room, no EncryptedSharedPreferences. Session tokens, FCM tokens, user role, and cached state currently survive a config-change only because they live in memory in `RootNode`.
5. **No FCM integration.** Push is a non-negotiable for emergency dispatch. Not wired.
6. **No background location.** `FOREGROUND_SERVICE_LOCATION` is requested in `AndroidManifest.xml` but no `LocationForegroundService` exists.
7. **No permission flow.** Location, notification, biometric, and "ignore battery optimization" prompts have no UI.
8. **No real auth.** The Login `authenticate` lambda defaults to `Failure(UNKNOWN)`; no token persisted; no `Authorization: Bearer` interceptor; no refresh path.
9. **No incident detail screen.** Card → detail navigation is missing for both admin alerts and user alert history.
10. **No onboarding / app-tour.** First-time-user experience is "splash → login".
11. **No real navigation.** Every nav action is a callback-prop drilled through constructors. With ~5 nodes that's fine; with 30+ it's a maintenance trap. Either commit to the in-house Nodes pattern *and* extend it with a typed back-stack, or switch to `androidx.navigation.compose`.
12. **No real error / loading / empty composables.** Each feature reinvents them.
13. **No tests.** No unit, no integration, no instrumentation, no Compose UI tests. MockK is in `MODULE.bazel`; nothing uses it.
14. **No CI.** `scripts/bazel_diff.sh` is referenced but missing from disk per `BUILD.bazel` comment.
15. **No release signing / Play Store config.** The `android_binary` is debug-only.

---

## 9. Security & Architecture Findings

### Strong points (don't change)
- **Privacy-first H3 indexing.** `LocationPrivacyFilter` uses `SecureRandom` + Box-Muller for *true Gaussian* noise; sigma is per-call uniform-random from [0.5km, 1.0km], preventing trilateration across observations. Distances are rounded to nearest 100m with a 100m floor before any UI surface. This is genuinely well-designed.
- **Explicit privacy boundary.** The phrase "exact GPS may only be surfaced when `EmergencyState.isActiveEmergency`" is enforced at multiple choke-points (`EmergencyAlertEngine.onIncomingAlert`, `ResponderMapView` parameter contract, `UserDashboardView` gate).
- **Lifecycle-safe disposal.** Every `Interactor` uses `CompositeDisposable` + `autoDispose()`.
- **State-machine emergency phases.** `EmergencyState.Phase` is a strict, explicit lifecycle.
- **NullAway + ErrorProne** wired into the Kotlin compilation as a `kt_compiler_plugin`.

### Risks / gaps

| Severity | Finding |
|---|---|
| **HIGH** | No certificate pinning planned for the HTTPS client. Emergency platforms are prime MITM targets. |
| **HIGH** | No JWT validation / expiry handling on the client. Token-refresh interceptor missing. |
| **HIGH** | `androidx.security:security-crypto:1.1.0-alpha06` is alpha and **deprecated by Google**. Plan to use Tink directly or DataStore + Android Keystore. |
| **HIGH** | No backend rate-limiting in front of `/auth/login`, `/auth/otp/request`, `/auth/password-reset/request`. amanah18 has the `RateLimitError` class but no middleware visible. |
| **HIGH** | Single-process in-memory `ConnectionManager` in amanah18 means a single backend instance only. Scaling out requires Redis pub/sub. |
| **MED**  | `MAPS_API_KEY` is read from manifest placeholder — make sure it's not committed and key restrictions (package + SHA-1) are enabled. |
| **MED**  | The admin `LoginNewsPublisher` branches on `user.role.name == "ADMIN"` — string compare instead of enum compare (`UserRole.ADMIN`). Fragile. |
| **MED**  | `RootNode` stores `userDashboardNode?` as a `var` and references it from a callback; if the user logs out mid-emergency this nulls out the receiver of the next alert. Race window. |
| **MED**  | `EmergencyAlertEngine` accepts `wsPublish` as a constructor lambda that the caller does NOT wire (`UserDashboardInteractor.initializeUser` passes `{ }`). Outbound emergency broadcast is **completely dead today**. |
| **MED**  | `enableEdgeToEdge()` + custom system bar handling — needs verification for keyboard insets across all screens (LoginView uses `imePadding()`; others don't). |
| **LOW**  | `BuildConfig.DEBUG` is referenced in `AmanahApplication` but `BuildConfig` may not be generated unless `kt_android_library` is configured with `generate_buildconfig`. |
| **LOW**  | The custom `Node` framework offers no back-stack. `RootNode`'s navigation is one-shot: there's no way to go *back* from Admin Dashboard to Login except via logout. Predictable Back button (Android system Back gesture) is not handled. |
| **LOW**  | Hardcoded sample data inside `LoginFeature.kt`, `DashboardFeature.kt`, `AdminFeature.kt`, `UserFeature.kt` — easy to ship by accident. Wrap behind `BuildConfig.DEBUG` or move to a test fixture. |
| **LOW**  | No `ProGuard`/`R8` rules. Scarlet, Gson, and Reaktive all need keep rules. |

---

## 10. Customer Demo Readiness Plan

### Goal
A 5-minute clickable demo where the presenter can:
1. Show the splash + branding.
2. Walk through a 3-screen onboarding.
3. Sign in (admin OR user).
4. (as user) Trigger a fake SOS, watch the responder map populate with a moving fake responder, see the ETA card.
5. (as admin) See the same alert appear live in the alert log, approve a pending user, then resolve the alert.
6. Sign out cleanly.

### What is needed for that

| # | Item | Effort (eng-days) | Owner |
|---|---|---|---|
| 1 | Delete dead `AppNode` + Islamic dashboard subtree | 0.25 | any |
| 2 | Onboarding flow (3 screens) | 1.0 | UI |
| 3 | Design-system primitives: `AmanahCard`, `AmanahPrimaryButton`, `AmanahErrorBanner`, `AmanahLoading`, `AmanahEmpty`, `AmanahErrorState`, `AmanahSpacing`, `AmanahMotion` | 1.5 | UI |
| 4 | Real Splash logo asset (replace the placeholder Arabic glyph) | 0.25 | design |
| 5 | DI graph: `AppComponent` (Dagger or manual) | 1.0 | infra |
| 6 | OkHttp + Retrofit + auth interceptor + token store | 1.5 | infra |
| 7 | Scarlet WebSocket factory wired into a singleton | 0.5 | infra |
| 8 | Backend redeploy from amanah18 (docker-compose) | 0.5 | infra |
| 9 | Wire LoginFeature `authenticate` to `AuthRepository → POST /auth/login` | 0.5 | feature-auth |
| 10 | Wire `UserFeature.loadNearbyUsers()` to `/users/nearby` (new endpoint or replace stub) | 1.0 | feature-user |
| 11 | Wire `EmergencyAlertEngine.wsPublish` to `AmanahWebSocketService.publishEmergencyAlert` | 0.5 | feature-emergency |
| 12 | Fake-responder demo dispatcher: backend script that emits 5 staged `responder_location` WS messages so the map animates during the demo | 0.5 | infra |
| 13 | Incident-detail node (drill-down from alert history and admin alert log) | 1.5 | feature-user + feature-admin |
| 14 | Admin "Approve User" wired to `POST /admin/approvals/{id}/approve` | 0.5 | feature-admin |
| 15 | Toaster / global snackbar wired (currently has `/* wire to global toast */` TODO) | 0.5 | infra |
| 16 | Permission prompts (location + notification) | 0.5 | feature-core |
| 17 | Smoke instrumentation test exercising the demo path | 0.5 | QA |

**Demo-ready total: ≈12 engineer-days. With 2 engineers, ≈6 working days.**

---

## 11. Immediate Priority Tasks (next 7 days)

In strict order. Each is independent enough to be a PR.

**Day 1 — Clean & align**
1. Delete [app/src/main/kotlin/com/amanah/app/node/AppNode.kt](app/src/main/kotlin/com/amanah/app/node/AppNode.kt) and [feature-core/src/main/kotlin/com/amanah/feature/core/mvi/DashboardFeature.kt](feature-core/src/main/kotlin/com/amanah/feature/core/mvi/DashboardFeature.kt) (the Islamic-modules dashboard). The product is a community-safety app, not an Islamic-app. If Islamic features are wanted later, they go into a separate optional module.
2. Delete the `splash → "Dashboard"` path in any code that still references it.
3. Move all hard-coded stub users (`Aisha`, `Omar`, etc.) into `app/src/debug/kotlin/.../debug/DebugFixtures.kt` and gate behind `BuildConfig.DEBUG`.
4. Add a `DESIGN.md` token list (colors, spacing, elevation, motion, typography) — content already exists, just centralise.

**Day 2 — Reusable widgets**
5. Create [feature-core/src/main/kotlin/com/amanah/feature/core/ui/](feature-core/src/main/kotlin/com/amanah/feature/core/ui/):
   - `AmanahSpacing.kt`, `AmanahMotion.kt`, `AmanahElevation.kt`
   - `AmanahPrimaryButton.kt`, `AmanahSecondaryButton.kt`, `AmanahDestructiveButton.kt`
   - `AmanahCard.kt`
   - `AmanahLoadingState.kt`, `AmanahEmptyState.kt`, `AmanahErrorState.kt`
   - `AmanahScaffold.kt` (top app bar + snackbar host + bottom bar slot, all wired to a global `GlobalSnackbarBus`)
6. Refactor `LoginView`, `DashboardView`, `UserDashboardView`, `AdminDashboardView` to use the new primitives. Net LOC should *decrease*.

**Day 3 — DI + Networking**
7. Create `app/src/main/kotlin/com/amanah/app/di/AppComponent.kt` (Dagger) with: `OkHttpClient`, `Retrofit`, `ApiService`, `TokenStore` (EncryptedSharedPreferences or DataStore + Tink), `AmanahWebSocketService` (built via `ScarletFactory`).
8. Add `AuthInterceptor` that injects `Authorization: Bearer <token>` and a `RefreshInterceptor` that handles 401 → `/auth/refresh` → retry.
9. Wire the `AppComponent` into `AmanahApplication.onCreate()`.

**Day 4 — Backend up**
10. `git clone` amanah18 backend into `backend/` (or vendor as a submodule). Write a `docker-compose.yml` at repo root that brings up PostgreSQL+PostGIS, Redis, the FastAPI app, and a Celery worker.
11. Run `alembic upgrade head`. Seed an admin user.
12. Verify `curl http://localhost:8000/api/v1/health` works and `wscat -c "ws://localhost:8000/ws?token=$TOKEN"` connects.

**Day 5 — Wire login + dashboard**
13. Create `feature-auth/repository/AuthRepository.kt` that calls `ApiService.login(LoginRequest)`.
14. Inject `AuthRepository` into `LoginFeature` (replace the stub `authenticate` lambda).
15. Persist the access + refresh tokens via `TokenStore` on success.
16. Replace the `RootNode`-managed `AuthenticatedUser` with a `SessionManager` that exposes a `Reaktive` `Observable<Session>`.

**Day 6 — Real emergency flow**
17. Implement `feature-user/repository/UserRepository.kt` with `getNearbyActiveUsers()`, `getAlertHistory()`, `getProfile()`.
18. Wire `EmergencyAlertEngine.wsPublish` to `webSocketService.publishEmergencyAlert(...)`.
19. Wire `webSocketService.observeEmergencyAlerts()` → `engine.onIncomingAlert(...)`.
20. Add a backend cron / admin tool to inject a *fake responder* for demos.

**Day 7 — Demo polish**
21. Implement onboarding 3-screen flow ([feature-auth/.../onboarding/](feature-auth/src/main/kotlin/com/amanah/feature/auth/node/onboarding/)).
22. Implement IncidentDetailNode for both user and admin.
23. Add permission flow (location + notification) on first launch.
24. Run a dry-run of the demo script end-to-end. File any P0 bugs. Cut a `release-candidate-demo-1` tag.

---

## 12. MVP Completion Plan (weeks 2–4)

### Week 2 — Repository layer + persistence
- Implement repositories for every feature: `AuthRepository`, `UserRepository`, `EmergencyRepository`, `AdminRepository`, `TrustedContactsRepository`, `NotificationsRepository`, `DeviceRepository`.
- Implement local cache via Room (or DataStore for simple key-value).
- Implement offline queue for emergency triggers (durable enough to survive process death).
- Wire FCM: device token registration → `POST /api/v1/devices`, push handler → emit into `WebSocketMessage` stream.

### Week 3 — Missing critical features
- **Trusted Contacts** (port from amanah18 Flutter): list, add, edit, delete, transfer.
- **Profile editing + verification flow** (email + phone OTP).
- **Onboarding** real screens with brand assets.
- **Settings real flows**: notification preferences, location precision, language (EN/AR/BN at minimum), about/legal.
- **Background location service** (foreground notification while emergency active).
- **Battery-aware location updates** (vary update interval by responder/idle state).

### Week 4 — Admin completeness
- Approvals workflow with diff view.
- Audit log viewer.
- Organisations / regions / roles management (already designed in admin-panel; port screens).
- Real-time alert log with WebSocket subscription.
- Force-resolve / escalation actions with reason capture.

---

## 13. Production Readiness Plan (months 2–3)

| Area | Tasks |
|---|---|
| **Security** | Cert pinning; key rotation; JWT key rotation; rate-limit middleware; secret manager (Vault / cloud KMS); SBOM + dependency scanning (Trivy + Snyk); penetration test |
| **Reliability** | Multi-instance WebSocket via Redis pub/sub; Postgres HA (replica + PgBouncer); Celery autoscale; canary deploys |
| **Observability** | Sentry SDK in client + backend; Prometheus exporters; Grafana dashboards (request rate, p95 latency, WS connections, alert rate); Loki for logs; alerting on SLOs |
| **CI/CD** | GitHub Actions: `bazel test`, `bazel build //app:amanah` for PRs; `ktlint` + `detekt`; Backend: `pytest`, `ruff`, `mypy`, `alembic check`; auto-deploy main → staging; manual gate → prod |
| **Performance** | Compose `recomposition` profiling under emergency load; map marker pooling at 100+ markers; backend connection-pool sizing; Redis cache hit rate ≥ 90% on hot endpoints |
| **Privacy / Compliance** | Privacy policy + ToS hosted; in-app data export + deletion (GDPR Article 15/17); audit retention 24 months; PII inventory documented; DPIA if EU launch |
| **Scaling** | k6 load test 10K concurrent WS; backend horizontal scale; CDN for static assets; Postgres read replica for analytics |
| **Internationalisation** | EN, AR, BN strings.xml; RTL layout testing (already `supportsRtl="true"`); ICU pluralisation |
| **Accessibility** | TalkBack walk-through; large text scaling; high-contrast theme; 48dp min touch targets verified |
| **Release** | Signing config; Play Console store listing; Play App Signing key; alpha → closed beta → open beta → prod ladder |

---

## 14. Recommended Final Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                       Mobile (Android)                       │
│                                                              │
│   app/                                                       │
│    └ AppComponent (Dagger)                                   │
│        ├ SessionManager  ────┐                               │
│        ├ ApiService          │                               │
│        ├ AmanahWebSocketSvc  │ shared singletons             │
│        ├ TokenStore          │                               │
│        ├ LocationProvider    │                               │
│        ├ FcmHandler          │                               │
│        └ GlobalSnackbarBus   ┘                               │
│                                                              │
│   feature-auth   feature-core   feature-user                 │
│   feature-admin  feature-emergency                           │
│        │              │              │                       │
│        ├ node/        ├ node/        ├ node/                 │
│        ├ mvi/         ├ mvi/         ├ mvi/                  │
│        ├ repo/   ←──  ApiService                             │
│        └ model/                                              │
│                                                              │
│   libraries/                                                 │
│     nodes-framework   location (H3)   ui (shared widgets)    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                 │ HTTPS + WSS (JWT)
                 ▼
┌──────────────────────────────────────────────────────────────┐
│                  Backend (FastAPI, Python)                   │
│   /api/v1/auth,users,incidents,responders,otp,devices,       │
│   /api/v1/admin,notifications,password-reset                 │
│   /ws (WebSocket: alerts, locations, status, presence)       │
└──────────────────────────────────────────────────────────────┘
       │           │            │              │
       ▼           ▼            ▼              ▼
   Postgres   Redis      Celery        FCM (Google)
   +PostGIS  (pub/sub)  (workers)     (push push)
```

Key principles:
- **Single Activity, Compose-only UI.** Already the case.
- **Single source of truth = MVICore `Feature`.** Each feature owns its state.
- **Repositories isolate the network/DB boundary.** Nothing above the repo knows about Retrofit, Scarlet, Room, or DataStore.
- **One global WebSocket connection**, multiplexed by topic, shared across features.
- **All side-effecting navigation goes through `News`** (MVICore), never through direct `Node` calls.
- **Privacy invariants enforced at the engine layer**, not the UI layer.
- **All DI is constructor-based.** Dagger provides the construction. No `Singleton.getInstance()`.

---

## 15. Suggested Refactors

| Refactor | Why | Where |
|---|---|---|
| Delete `AppNode` + `DashboardFeature` (Islamic) | Conflicts with product identity; dead code | [app/.../node/AppNode.kt](app/src/main/kotlin/com/amanah/app/node/AppNode.kt), [feature-core/.../mvi/DashboardFeature.kt](feature-core/src/main/kotlin/com/amanah/feature/core/mvi/DashboardFeature.kt) |
| Extract `LoginEvent = LoginWish` typealias into a proper sealed class | The typealias shadows the import line below it and is fragile | [feature-auth/.../node/login/LoginView.kt:54-61](feature-auth/src/main/kotlin/com/amanah/feature/auth/node/login/LoginView.kt#L54-L61) |
| Move stub data behind `BuildConfig.DEBUG` or move to `app/src/debug/` | Ships fake `Aisha`/`Omar` users to release builds | [feature-user/.../UserFeature.kt:152-162](feature-user/src/main/kotlin/com/amanah/feature/user/mvi/UserFeature.kt#L152-L162), [feature-admin/.../AdminFeature.kt:81-91](feature-admin/src/main/kotlin/com/amanah/feature/admin/mvi/AdminFeature.kt#L81-L91) |
| Replace `news.user.role.name == "ADMIN"` with enum compare | String compare against enum is fragile | [feature-auth/.../LoginFeature.kt:142-145](feature-auth/src/main/kotlin/com/amanah/feature/auth/mvi/LoginFeature.kt#L142-L145) |
| Hoist all `Modifier.padding(16.dp)` to `AmanahSpacing.md` | Magic numbers everywhere | every `*View.kt` |
| Replace prop-drilled `onShowToast`/`onShowSnackbar` lambdas with a `GlobalSnackbarBus` (Reaktive Subject) | Reduces constructor noise; lets non-leaf nodes raise toasts | [app/.../node/RootNode.kt:106-108](app/src/main/kotlin/com/amanah/app/node/RootNode.kt#L106-L108), [app/.../node/AppNode.kt:50](app/src/main/kotlin/com/amanah/app/node/AppNode.kt#L50) |
| Inject `WeakHandler` via DI not via `NodeContext.weakHandler` | The `NodeContext` exposing `.weakHandler` is a smell | [feature-user/.../UserDashboardNode.kt:24](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/UserDashboardNode.kt#L24) |
| Convert `Node`'s `view.events = lambda` mutable pattern to a Reaktive `PublishSubject<Event>` | Mutable nullable lambda is a foot-gun and prevents replay | [feature-auth/.../LoginView.kt:65](feature-auth/src/main/kotlin/com/amanah/feature/auth/node/login/LoginView.kt#L65), [libraries/nodes-framework/.../NodeView.kt](libraries/nodes-framework/src/main/kotlin/com/amanah/lib/nodes/NodeView.kt) |
| Either commit to the in-house `Node`/`Router`/`Interactor` and add a back-stack, OR migrate to `androidx.navigation.compose` | The current pattern has no Back-button handling and no nested-graph support | [libraries/nodes-framework/](libraries/nodes-framework/) |
| Unify Compose imports — currently each file has 30-50 imports; use `*` package imports where reasonable, or move shared Compose imports into a base composable | Readability and merge-conflict reduction | every `*View.kt` |
| Replace inline `java.util.UUID.randomUUID().toString()` and `java.text.SimpleDateFormat` with idiomatic Kotlin (`kotlin.uuid` or stable wrappers) | Java-isms scattered | [EmergencyAlertEngine.kt:177](feature-emergency/src/main/kotlin/com/amanah/feature/emergency/engine/EmergencyAlertEngine.kt#L177), [AdminDashboardView.kt:271](feature-admin/src/main/kotlin/com/amanah/feature/admin/node/dashboard/AdminDashboardView.kt#L271) |
| Inject `Clock` (interface returning current time) so unit tests can fast-forward | Tests of timestamps are hard | many `System.currentTimeMillis()` call sites |
| Make `EmergencyState.Phase` exhaustive removal of `ACTIVE_EMERGENCY` (wire-compat alias) | Already documented as alias; eliminating reduces the number of phases the UI must handle | [EmergencyFeature.kt:45-62](feature-emergency/src/main/kotlin/com/amanah/feature/emergency/mvi/EmergencyFeature.kt#L45-L62) |

---

## 16. Folder / File-Level Recommendations

Recommended target tree:

```
Amanah_App/
├── app/                                     # composition root + DI
│   └── src/main/kotlin/com/amanah/app/
│       ├── AmanahApplication.kt
│       ├── MainActivity.kt
│       ├── di/                              # Dagger components & modules
│       │   ├── AppComponent.kt
│       │   ├── NetworkModule.kt
│       │   ├── WebSocketModule.kt
│       │   ├── StorageModule.kt
│       │   └── SessionModule.kt
│       └── node/
│           └── RootNode.kt
├── backend/                                 # FastAPI app from amanah18 (vendored)
│   ├── app/...
│   ├── alembic/...
│   └── docker-compose.yml
├── feature-auth/
│   └── src/main/kotlin/com/amanah/feature/auth/
│       ├── node/
│       │   ├── login/
│       │   ├── onboarding/                  # NEW (3 screens)
│       │   ├── passwordreset/
│       │   └── permission/                  # NEW (location + push prompts)
│       ├── mvi/
│       ├── model/
│       └── repository/                      # NEW
├── feature-core/
│   └── src/main/kotlin/com/amanah/feature/core/
│       ├── theme/
│       ├── ui/                              # NEW: AmanahCard, AmanahPrimaryButton, ...
│       ├── snackbar/                        # NEW: GlobalSnackbarBus
│       ├── network/                         # NEW: ApiService, interceptors
│       ├── websocket/
│       ├── session/                         # NEW: SessionManager
│       ├── storage/                         # NEW: TokenStore, KeyValueStore
│       ├── location/                        # background service + LocationProvider
│       ├── push/                            # NEW: FcmHandler
│       └── debug/                           # AmanahDebugDrawer (existing)
├── feature-user/
│   └── src/main/kotlin/com/amanah/feature/user/
│       ├── node/
│       │   ├── dashboard/
│       │   ├── alerthistory/                # NEW
│       │   ├── incidentdetail/              # NEW (user side)
│       │   ├── profile/                     # MOVE & expand
│       │   ├── trustedcontacts/             # NEW (port from amanah18 Flutter)
│       │   └── settings/                    # NEW (real)
│       ├── mvi/
│       ├── model/
│       └── repository/                      # NEW
├── feature-admin/
│   └── src/main/kotlin/com/amanah/feature/admin/
│       ├── node/
│       │   ├── dashboard/
│       │   ├── approvals/                   # NEW
│       │   ├── userdetail/                  # NEW (incl. edit + audit)
│       │   ├── alertdetail/                 # NEW
│       │   ├── auditlog/                    # NEW
│       │   ├── organisations/               # NEW
│       │   ├── regions/                     # NEW
│       │   └── roles/                       # NEW
│       ├── mvi/
│       ├── model/
│       └── repository/                      # NEW
├── feature-emergency/
│   └── (mostly unchanged; add `repository/` and `wsBridge/`)
├── libraries/
│   ├── nodes-framework/                     # ADD: BackStack, ChildAttacher
│   ├── location/
│   └── network-test/                        # NEW: fake server harness
└── scripts/
    ├── bazel_diff.sh
    ├── seed_demo_data.sh                    # NEW
    └── ci/                                  # NEW
```

**Files to delete now (no replacement):**
- [app/src/main/kotlin/com/amanah/app/node/AppNode.kt](app/src/main/kotlin/com/amanah/app/node/AppNode.kt) — orphaned root.
- [feature-core/src/main/kotlin/com/amanah/feature/core/mvi/DashboardFeature.kt](feature-core/src/main/kotlin/com/amanah/feature/core/mvi/DashboardFeature.kt) — Islamic-modules feature; the entry list doesn't belong here.
- [feature-core/src/main/kotlin/com/amanah/feature/core/node/dashboard/](feature-core/src/main/kotlin/com/amanah/feature/core/node/dashboard/) — its only consumer is `AppNode`.
- [feature-core/src/main/kotlin/com/amanah/feature/core/geo/H3LocationIndex.kt](feature-core/src/main/kotlin/com/amanah/feature/core/geo/H3LocationIndex.kt) — duplicate of [libraries/location/.../H3LocationIndex.kt](libraries/location/src/main/kotlin/com/amanah/lib/location/H3LocationIndex.kt). Keep the `libraries/location` copy; delete the `feature-core/geo/` copy.

**Files to substantially rewrite:**
- [feature-auth/src/main/kotlin/com/amanah/feature/auth/node/login/LoginView.kt](feature-auth/src/main/kotlin/com/amanah/feature/auth/node/login/LoginView.kt) — adopt `AmanahScaffold`, remove the `typealias LoginEvent = LoginWish` workaround.
- [app/src/main/kotlin/com/amanah/app/node/RootNode.kt](app/src/main/kotlin/com/amanah/app/node/RootNode.kt) — once a session manager exists, this becomes a much smaller router that reacts to `SessionManager.state` instead of accepting per-screen callbacks.

---

## 17. Final Action Plan

```
WEEK 1  ── Foundations (customer demo)
   Day 1: clean dead code + design tokens
   Day 2: reusable widgets
   Day 3: DI + networking
   Day 4: backend redeploy
   Day 5: wire login + dashboard
   Day 6: wire emergency flow
   Day 7: onboarding + incident detail + demo dry-run
                       ───── DEMO MILESTONE ─────

WEEK 2-4 ── MVP Completion
   - Repository layer (all features)
   - Persistence (Room or DataStore + Tink)
   - FCM
   - Trusted Contacts
   - Profile + verification (phone + email OTP)
   - Background location service
   - Admin completeness (approvals, audit, orgs/regions/roles)

MONTH 2 ── Hardening
   - Cert pinning, key rotation, rate-limiting
   - Multi-instance WebSocket via Redis pub/sub
   - Observability stack (Sentry + Prometheus + Grafana + Loki)
   - CI/CD (GitHub Actions)
   - Test coverage (target ≥ 60% on critical paths)

MONTH 3 ── Production
   - Privacy/compliance (privacy policy, GDPR data export/delete)
   - Performance + load test (k6: 10K WS)
   - i18n (EN, AR, BN) + accessibility audit
   - Release pipeline (alpha → closed beta → open beta → prod)
   - Penetration test + DPIA (if EU launch)

QUARTER 2 ── Scale
   - Multi-region backend
   - Postgres read replicas + PgBouncer
   - Push notification dedupe + delivery analytics
   - SDK for third-party integrations (police, hospital APIs)
   - Tablet + foldable layouts
   - Wear OS companion app for one-tap SOS
```

### One-sentence summary
*Amanah_App is a beautifully scaffolded Android client that has not yet been connected to anything. The fastest credible path forward is to redeploy the existing FastAPI backend, finish the design system, wire the data layer, and add four missing screens — all of which is ≈12 engineer-days of focused work.*

---

**Companion documents:**
- [UI_UX_MVP_PLAN.md](UI_UX_MVP_PLAN.md) — screen-by-screen UI roadmap
- [FEATURE_COMPLETION_MATRIX.md](FEATURE_COMPLETION_MATRIX.md) — feature-level status comparison
- [TECHNICAL_DEBT_REPORT.md](TECHNICAL_DEBT_REPORT.md) — debt + security + scalability findings
- [MIGRATION_PLAN_FROM_AMANAH18.md](MIGRATION_PLAN_FROM_AMANAH18.md) — what to port, what to leave behind

---

## Appendix — Work Completed in This Session (2026-05-21)

The audit above was followed by an execution pass that closed many of the P0
demo blockers. Status at end of session:

### Cleanup (Phase A)
- ✅ Deleted `app/node/AppNode.kt` (dead navigation root).
- ✅ Deleted `feature-core/node/dashboard/` (Islamic-modules dashboard subtree).
- ✅ Deleted `feature-core/mvi/DashboardFeature.kt` (Prayer/Quran/Zakat/Qibla).
- ✅ Deleted `feature-core/geo/H3LocationIndex.kt` (duplicate of libraries/location).
- ✅ Fixed dark-mode toggle icon copy-paste bug ([UserDashboardView.kt:137](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/UserDashboardView.kt#L137)).
- ✅ Fixed string-compare-against-enum bug ([LoginFeature.kt:142](feature-auth/src/main/kotlin/com/amanah/feature/auth/mvi/LoginFeature.kt#L142)).
- ✅ Updated `SplashNode` doc-comment that still referenced the deleted `AppNode`.

### Design system (Phases B + C + D)
- ✅ `feature-core/ui/AmanahSpacing.kt` (8 dp-based scale).
- ✅ `feature-core/ui/AmanahMotion.kt` (FAST/NORMAL/SLOW + Material 3 easings).
- ✅ `feature-core/ui/AmanahElevation.kt` (none → emergency).
- ✅ `feature-core/ui/AmanahTouch.kt` (48 dp minimum, button/input heights).
- ✅ `feature-core/ui/AmanahPrimaryButton.kt` — `AmanahPrimaryButton`, `AmanahSecondaryButton`, `AmanahDestructiveButton`.
- ✅ `feature-core/ui/AmanahCard.kt` — `AmanahCard`, `AmanahEmergencyCard`.
- ✅ `feature-core/ui/AmanahStateViews.kt` — `AmanahLoadingState`, `AmanahEmptyState`, `AmanahErrorState`.
- ✅ `feature-core/ui/AmanahScaffold.kt` — wired to `GlobalSnackbarBus`.
- ✅ `feature-core/ui/AmanahTopBar.kt` — branded top bar with back nav.
- ✅ `feature-core/ui/AmanahTextField.kt` — Outlined text field with error/password support.
- ✅ `feature-core/ui/AmanahStatusBadge.kt` — semantic status pills (NEUTRAL/POSITIVE/WARNING/CRITICAL).
- ✅ `feature-core/ui/AmanahConnectivityBanner.kt` — offline indicator.
- ✅ `feature-core/ui/GlobalSnackbarBus.kt` — process-wide snackbar bus (Reaktive PublishSubject).

### Backend vendoring (Phase E)
- ✅ amanah18 backend rsynced to `backend/` (excluding venvs / caches).
- ✅ Inherited working `docker-compose.yml` (postgres+postgis, redis, fastapi, celery).
- ✅ Alembic history preserved.

### Four new screens (Phases I + J + K + L)
- ✅ `feature-auth/node/onboarding/` — 3-page onboarding (Welcome → SOS → Privacy).
- ✅ `feature-user/node/incidentdetail/` — User incident detail with timeline + counts.
- ✅ `feature-admin/node/alertdetail/` — Admin alert detail with Google Maps + responder list + force-resolve flow.
- ✅ `feature-admin/node/userdetail/` — Admin user detail with identity, contact, devices, activity, approve/suspend actions.

### Networking + DI (Phases F + G + H)
- ✅ `feature-core/network/ApiService.kt` — full Retrofit surface mirroring the FastAPI v1 endpoints.
- ✅ `feature-core/network/AuthInterceptor.kt` — Bearer token injection (with public-endpoint allowlist).
- ✅ `feature-core/network/RefreshInterceptor.kt` — single-flight refresh-token rotation on 401.
- ✅ `feature-core/network/ApiFactory.kt` — OkHttp/Retrofit assembly.
- ✅ `feature-core/session/TokenStore.kt` — EncryptedSharedPreferences-backed token persistence.
- ✅ `feature-core/session/SessionManager.kt` — `Session` interface + BehaviorSubject stream.
- ✅ `feature-auth/repository/AuthRepository.kt` — Coroutines → Reaktive bridge; DTO → AuthenticatedUser mapping.
- ✅ `app/di/AppGraph.kt` — manual DI container (singleton lifetime); construction in `AmanahApplication.onCreate`.
- ✅ `MainActivity` wires `AppGraph` into `RootNode`.
- ✅ `LoginNode` accepts an optional `AuthRepository` and wires it into `LoginFeature.authenticate`.
- ✅ `UserDashboardNode` accepts an optional `AmanahWebSocketService`; engine's `wsPublish` now routes through the service.
- ✅ `EmergencyAlertEngine.wsPublish` is no longer a `// TODO` — outbound alerts publish a real `EmergencyAlertWireMessage`.
- ✅ Inbound `observeEmergencyAlerts()` and `observeResponderLocations()` are subscribed inside `UserDashboardInteractor.initializeUser`.

### Routing (RootNode rewrite)
- ✅ Splash → (first-launch) Onboarding → Login → role-gated dashboards.
- ✅ Admin → tap user → AdminUserDetail; Admin → tap alert → AdminAlertDetail.
- ✅ User → tap alert history → IncidentDetail.
- ✅ Global snackbar bus piped through `AppGraph` so any node can `graph.snackbarBus.post("...")`.

### Existing-view refactors (Phase M)
- ✅ `LoginView` migrated to `AmanahPrimaryButton`, `AmanahTextField`, `AmanahCard` and the spacing scale.

### Numbers
- Kotlin LOC grew from ~5,641 → ~8,122 (+44%).
- 46 new or modified Kotlin files.
- Zero references to deleted classes remain.

### Still outstanding (next session)
- Bazel build sanity check (no `bazel` on this box; verify on a dev machine).
- Hydrate persisted session on app start (currently always shows login).
- Wire `UserFeature.loadNearbyUsers()` to a real repo (still stubbed).
- Wire `AdminFeature.LoadAll` to `AdminRepository`.
- Wire the live WS feed of admin notifications into `AdminFeature.LiveAlertReceived`.
- Replace the `?token=` WS query param with header-based auth (TECHNICAL_DEBT_REPORT C9).
- FCM device registration.
- Foreground service for active emergencies.
- Tests (none yet — TECHNICAL_DEBT_REPORT E1).
- ProGuard / R8 rules.
- CI workflow.

### How to run the demo today
1. `cd backend && docker-compose up -d`
2. `docker-compose exec api alembic upgrade head`
3. `docker-compose exec api python create_admin.py` (or similar seed script — see `backend/HOW_TO_CREATE_ADMIN.md`).
4. `bazel build //app:amanah && bazel mobile-install //app:amanah`
5. Open the app on the emulator. Splash → Onboarding (3 pages) → Login. Sign in with the seeded admin and a seeded user on a second device/emulator to demo the full flow.

