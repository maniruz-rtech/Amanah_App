# Amanah App — Project State (audit 2026-09-26, updated after modernization 2026-09-27)

Compact restart record. Evidence-based; read-only audit, nothing was modified or deleted.
Confidence tags: **[V]** verified by running/reading code, **[R]** read only, **[?]** not verified.


## 0. Current status (2026-09-27, after data-model + login pass — authoritative; supersedes conflicting text below)
Details: [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) · [KNOWN_ISSUES.md](KNOWN_ISSUES.md) · [UPGRADE_LOG.md](UPGRADE_LOG.md) · [DEPENDENCY_VERSIONS.md](DEPENDENCY_VERSIONS.md).

- **Builds/tests:** `bazel build //app:amanah` ✅ · `bazel test //...` 6/6 ✅ · backend `pytest` **178 passed, 0 failed** ✅ · `alembic check` clean ✅ · Docker stack (PG 18.6/PostGIS 3.6.4, Redis 8.10.2) healthy ✅.
- **`User.status`:** persisted enum lifecycle state (see DEVELOPMENT_STATUS); flags remain the enforcement layer, kept in sync.
- **Migrations:** 008 reconciles all model/schema drift (fresh, existing-with-data and legacy create_all+stamp DBs all converge); 009 = device identity + encrypted TOTP + `created_by_id`. `tests/test_migrations.py` prevents future drift.
- **Auth/device:** backend login registers/binds the device; Android sends a stable per-install `device_uuid` + `platform`; verified end-to-end with the app's real network stack against the live backend.
- **Not verified:** the APK on a device/emulator (no KVM on this host).
- **Still open (see KNOWN_ISSUES):** no FCM/Maps/cert-pin config, no registration flow, `/admin/users` 500, Android↔backend profile/admin contract gaps, verification PIN unimplemented, rate limiting not wired, dev secrets to rotate, no git repo.

**Next recommended task:** run the APK on a KVM-capable host/device and fix the UI-level gaps that surfaces; then the `/admin/users` 500 + profile DTO alignment.

---

## 1. What it is
Emergency/SOS community-safety app. Android client (Kotlin, Compose, Badoo MVICore + custom "Nodes" framework, manual DI) + FastAPI/PostgreSQL(PostGIS)/Redis/Celery backend. Roles: user, responder, admin.
Size: ~11.5k LOC Kotlin (119 files, 5 feature modules + 2 libraries + app), ~110 Python files. **[V]**

## 2. Build state (PRE-UPGRADE snapshot — see §0 for current)
| Item | Finding |
|---|---|
| Android build system | Bazel 7.4.1 (`.bazelversion`) via Bzlmod (`MODULE.bazel`) + tiny legacy `WORKSPACE`. **No Gradle anywhere.** Bazel is the only Android build, so it is REQUIRED for the app. |
| Toolchain | rules_kotlin 2.1.0, Kotlin 2.1.0, rules_android 0.6.0, compileSdk/target 35, minSdk 26, JDK 17, SDK at `/home/mzaman/Android/Sdk` (hardcoded in `.bazelrc`). |
| `bazel query //...` | OK, 27 targets. **No test targets exist** (tests in `src/test` are not wired to any `kt_*_test`). |
| `bazel build //app:amanah` | **FAILS** (analysis OK; 1917 actions, all libs compile except feature-user). |
| Failure | `feature-user/.../UserDashboardInteractor.kt:188` `gateway.incoming.subscribe { }` — Reaktive `subscribe` extension not imported (Observable overload mismatch); `:213` `.autoDispose()` ambiguous (Reaktive `Disposable` vs RxJava2 `Disposable`, both defined in `libraries/nodes-framework/.../Interactor.kt:49-50`). Blocks `//app`. |
| Likely next failure **[?]** | `app/AmanahApplication.kt` uses `BuildConfig.DEBUG`; Bazel does not generate BuildConfig for `kt_android_library`. Unverifiable until feature-user compiles. |
| Backend | Python 3.12 venv installs cleanly from `requirements.txt`; `import app.main` OK **[V]**. |
| Backend tests | `pytest`: **35 passed, 127 errors**. Cause: no `tests/conftest.py` (fixtures `db_session`, `test_user`, … missing); `tests/unit/` and `tests/security/` are empty. |
| Migrations | Alembic linear 001→007, no branching **[R]**; not run against a DB. |
| Local runtime | Docker: `amanah_api` (image 4 months old), celery worker+beat (**unhealthy**), postgis 5434, redis 6380. Not the current source tree. |
| Not a git repo | `/home/mzaman/Amanah_App` has **no `.git`** (no history, no branches, can't diff or restore). Section 16 of the task (git health) can't be done until `git init`. |

## 2b. Dependency notes
- `maven_install.json` is a **dead placeholder** (empty `dependencies`, version 0.1.0); `lock_file` is commented out in MODULE.bazel → builds are **not reproducible/pinned**. Regenerate with `bazel run @maven//:pin` or delete. Also `MODULE.bazel.lock` is tracked.
- Android deps are ~1 year old: Compose 1.7.5 (BOM 2024.09), AGP n/a, Kotlin 2.1.0, OkHttp 4.12, Retrofit 2.11, Firebase-messaging 24.0.0, Tink 1.13, Dagger 2.52. **Dagger is declared but unused** (DI is manual `AppGraph`). `kotlinx-serialization-json`, `statemachine` (Tinder), `biometric`, `navigation-compose`, `viewmodel-compose`, `maps-compose*` likely unused/underused **[?]** — verify per-module before removal. MVICore 1.4.0 (JitPack, unmaintained) is a structural dependency: do NOT drop.
- Backend pins are ~2 years old (fastapi 0.109, starlette 0.36 — old CVE-bearing range, pydantic 2.6, sqlalchemy 2.0.25, python-jose 3.3.0 (known CVEs, unmaintained-ish), passlib 1.7.4 (unmaintained), sentry-sdk 1.40, celery 5.3.6). `aioredis==2.0.1` is deprecated/merged into redis-py and probably unused; `psycopg2-binary` duplicated by `asyncpg` (needed only for Alembic if sync). Root `requirements.txt` (h3, causalml, orbit-ml, pandas, numpy, gitpython, protobuf) is **unrelated to the backend** — leftover scaffold, PROBABLY_UNUSED.
- Upgrade order (not now): (1) fix build, (2) pin maven, (3) backend security bumps (starlette/fastapi, python-jose→pyjwt/authlib), (4) Compose/Kotlin later.

## 3. Architecture map
```
app/                 RootNode (screen state machine) + AppGraph (manual DI) + MainActivity/AmanahApplication
libraries/nodes-framework   Node/Interactor/Router/View base (Uber-RIBs-like)
libraries/location          H3 index, LocationPrivacyFilter
feature-core         theme, UI kit, Retrofit ApiService (25 endpoints), Tink token store, OkHttp WS gateway,
                     durable outbound queue, FCM service, foreground service, splash, debug drawer
feature-auth         Login (+Onboarding, PasswordReset UI)      feature-user   dashboard, incident detail, repos
feature-admin        dashboard, alert detail, user detail        feature-emergency  alert engine, H3 proximity, repos
backend/app          api/v1 (10 routers) → services → repositories → db/models (18 tables); WebSocket /ws; Celery tasks
```

## 4. Feature status (vocabulary from task)
| Module | Status | Evidence |
|---|---|---|
| feature-core | PARTIAL, not compiled into a running app | compiles in Bazel; only 3 unit tests (unwired). |
| feature-auth | PARTIAL | Login wired to real `AuthRepository` in RootNode; **no registration UI, no OTP UI, PasswordReset UI has `TODO`, Onboarding not reachable [?]**. |
| feature-user | **BROKEN** (does not compile) | see build failure. Dashboard/incident UI otherwise present. |
| feature-admin | PARTIAL | compiles; client calls `/admin/users/{id}`, `/admin/users/{id}/approve`, `/admin/approvals` which **do not exist on backend**. |
| feature-emergency | PARTIAL | engine/proximity/repos compile; 1 test not runnable (no test target). |
| app | BLOCKED | can't link until feature-user compiles. |
| backend | PARTIAL / most complete part | 65+ endpoints; imports fine; tests mostly non-runnable (missing conftest). |

## 5. End-to-end flows
| Flow | Status | Why |
|---|---|---|
| Install app | BROKEN | build fails |
| Login → token → session | PARTIAL | code path exists; **cannot run**. Also: manifest has no `usesCleartextTraffic`/network-security-config, `AppGraph` default is `http://10.0.2.2:8000` → Android 9+ will block plain HTTP even in debug **[R, high confidence]**. |
| Registration | NOT_IMPLEMENTED | no client screen or endpoint (users created by admin/`create_admin.py`). |
| SOS create → backend → responders | PARTIAL | endpoints exist both sides; client-side SOS wiring lives in the non-compiling module. |
| Realtime WS | PARTIAL | client gateway OK; backend has **3 competing WS implementations** (`app/websocket.py` is the one mounted; `websocket_v2.py`, `api/v1/websocket.py`, `websockets/` package also exist). |
| Push (FCM) | NOT_WORKING | no `google-services.json`, no Firebase init in Bazel; backend `fcm_enabled=False`, no credentials. |
| Maps | NOT_WORKING | Maps API key is a hardcoded placeholder string in `app/BUILD.bazel`. |

## 6. API mismatches (client → backend)
Missing on backend: `POST /admin/users/{id}/approve`, `GET /admin/users/{id}`, `GET /admin/approvals`; client `POST /auth/password-reset/request` exists but flow differs from `/password-reset/*` router (two overlapping designs: `/auth/password-reset/*` vs `/password-reset/*`, and `/auth/otp/*` vs `/otp/*`). Duplicate device APIs: `/users/devices` vs `/devices`. Backend endpoints without client: MFA (setup/confirm/verify/delete), trusted-contacts create/patch/delete, `/responders/availability` PUT, `/nearby-incidents`, `/my-assignments`, admin org/region/role endpoints. Full per-endpoint table not yet built.

## 7. Security findings (no values reproduced)
- SECRET FOUND — LOCATION: `backend/.env` — TYPE: JWT signing key, DB password, encryption key (dev values, weak-looking) — SEVERITY: MEDIUM (dev env; HIGH if reused in prod) — ACTION: rotate, keep out of any repo; `.env` is not in a git repo now but must be gitignored.
- `docker-compose.yml` and `config.py` ship **default fallback secrets** (`dev-secret-key-change-in-production`, `CHANGE-ME…`): app should refuse to start in `staging/production` with defaults. **[R]**
- `.env.example` in `backend/` is fine (no real values checked in detail **[?]**).
- Maps key placeholder in BUILD.bazel: not a secret, but is a release blocker.
- Cert pinning: placeholders intentionally fail-closed in release (good); must be filled before release.
- CORS `allow_methods/headers=["*"]` with credentials; docs/OpenAPI gated on `debug` (good).
- Logged stack trace at 2026-04-17 `'User' object has no attribute 'status'` (backend.log) — bug, may be fixed since.
- Not done yet: authz review of each endpoint, SQL-injection review (SQLAlchemy ORM used → low), token in WS handshake (client uses header; backend may accept query token — check), input validation review.

## 8. Cleanup classification (NOTHING DELETED — awaiting approval)
| Path | Class | Evidence |
|---|---|---|
| `bazel-*` symlinks (4) | SAFE_TO_DELETE (generated; already in `.gitignore`) | point into `~/.cache/bazel`, machine-specific, recreated on build. Deleting is harmless but pointless. |
| `backend/backend.log`, `backend.pid` | SAFE_TO_DELETE | stale (Apr 17), PID file for a dead process. |
| `backend/celerybeat-schedule` | SAFE_TO_DELETE / gitignore | runtime state file, rewritten by celery beat. |
| `requirements.txt` (repo root) | PROBABLY_UNUSED | ML/geo stack unrelated to code; nothing references it. |
| `maven_install.json` | PROBABLY_UNUSED | empty placeholder; referenced only by commented-out `lock_file`. Replace, don't keep. |
| `backend/app/websocket_v2.py`, `app/api/v1/websocket.py` | PROBABLY_UNUSED | not imported by `main.py` (grep). Confirm then delete. |
| `backend/app/websockets/` | POSSIBLY_REQUIRED | used by `tests/integration/test_notifications_websockets.py` only; overlaps `app/websocket.py`. Consolidate. |
| `backend/tests/{unit,security}/` | empty dirs | keep, fill. |
| `dagger`/`dagger-compiler` maven entries | PROBABLY_UNUSED | manual DI in `AppGraph`. |
| `WORKSPACE` | POSSIBLY_REQUIRED | comment claims android toolchain need; test by removal in a copy. |
| Docs: 8k lines across 39 .md | see §9 | heavily redundant. |
| `backend/.env` | REQUIRED locally, never commit | |
| `libraries/*`, `app`, `feature-*` | REQUIRED | |

## 9. Documentation reconciliation (partial — sample-checked, not exhaustive)
| Claim | Reality | Verdict |
|---|---|---|
| FEATURE_COMPLETION_MATRIX: WS service in `feature-core/websocket/AmanahWebSocketService.kt`, `AmanahConnectionStateMachine.kt` | files do not exist; replaced by `realtime/OkHttpRealtimeGateway.kt` etc. | OUTDATED |
| Matrix: "authenticate stub" for login, "no token store" | RootNode passes real `AuthRepository`; Tink token store, refresh interceptor exist | OUTDATED |
| Matrix: "no foreground service", "no durable offline queue", "no FCM" | `EmergencyForegroundService`, `DurableOutboundQueue`, `AmanahFirebaseMessagingService` exist (untested at runtime) | OUTDATED |
| `docs/FINAL_MVP_COMPLETION_STATUS.md`, `PRODUCTION_READINESS_PLAN.md` etc. imply MVP complete | app does not build; tests don't run | FALSE/unsupported [?—not read in full] |
| `AppGraph`: manual DI because "Dagger needs kapt under Bazel" | true & consistent | MATCH |
| MODULE.bazel comments say "Bazel 8" | `.bazelversion` = 7.4.1 | OUTDATED |
The other ~35 docs (`docs/*`, `PROJECT_AUDIT_AND_ROADMAP.md`, `TECHNICAL_DEBT_REPORT.md`, `UI_UX_MVP_PLAN.md`, `MIGRATION_PLAN_FROM_AMANAH18.md`) are **not yet reconciled**; treat all as unverified history. Recommendation: keep, but move to `docs/archive/` and make this file + one README the source of truth.

## 10. Shortest path to a working app (proposed, needs approval)
1. `git init` + baseline commit (after adding `.gitignore` entries: `bazel-*`, `*.log`, `*.pid`, `celerybeat-schedule`, `.env`, `__pycache__/`, venvs). Everything below becomes reversible.
2. Fix `UserDashboardInteractor.kt` (import `com.badoo.reaktive.observable.subscribe`, disambiguate `autoDispose`) → rebuild → fix next errors (likely BuildConfig).
3. Add `network_security_config` allowing cleartext to `10.0.2.2` in debug only; set real base URL via build config.
4. Backend: add `tests/conftest.py` (test DB engine, `db_session`, `test_user`, client); get the 127 errors to run; restart docker stack from current source and fix unhealthy celery.
5. Add admin endpoints the client expects (or change client); pick one of the duplicate WS/OTP/password-reset/device API sets.
6. Add `kt_android_local_test` targets so existing 4 Kotlin tests run.
7. Then: registration flow, FCM (`google-services.json` handling), Maps key injection, cert pins, secrets management, dependency upgrades.

## 11. Open items / not covered in this pass
Per-endpoint API table, DB model↔DTO field-level mapping, unused resource/dependency detection by tool, docs claim-by-claim reconciliation, git history/secret scan (no git), deep authz review, Bazel `//...` test run (none defined), running the Android app on emulator.
