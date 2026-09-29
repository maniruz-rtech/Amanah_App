# Amanah_App — Technical Debt, Security & Scalability Report

Findings catalogued by severity. Each item has: where it lives, what's wrong, what to do, and an effort estimate.

---

## Severity Definitions

- **P0** — blocks demo / blocks production; ship-stopper
- **P1** — fix in MVP window (≤ 4 weeks)
- **P2** — fix in hardening window (months 2-3)
- **P3** — cleanup; nice-to-have

---

## A. Dead Code & Architectural Conflicts

### A1. [P0] Two divergent navigation roots
**Where:** [app/src/main/kotlin/com/amanah/app/node/RootNode.kt](app/src/main/kotlin/com/amanah/app/node/RootNode.kt) (used) vs. [app/src/main/kotlin/com/amanah/app/node/AppNode.kt](app/src/main/kotlin/com/amanah/app/node/AppNode.kt) (orphan).
**Issue:** `AppNode` wires a Splash → Islamic-modules-dashboard flow that contradicts the emergency-response product. `MainActivity` uses `RootNode`. `AppNode` and its consumer `DashboardNode`/`DashboardFeature` are dead.
**Fix:** Delete `AppNode.kt`, the `feature-core/.../node/dashboard/` directory, and `feature-core/.../mvi/DashboardFeature.kt`.
**Effort:** 0.25 d.

### A2. [P0] Islamic-features modules inside an emergency-response app
**Where:** [feature-core/.../mvi/DashboardFeature.kt:93-99](feature-core/src/main/kotlin/com/amanah/feature/core/mvi/DashboardFeature.kt#L93-L99) hard-codes Prayer Times, Quran, Zakat, Islamic Calendar, Qibla Finder.
**Issue:** Identity confusion. If both directions are intended, they need to be separate apps or feature-flagged modules.
**Fix:** Delete (see A1). If retained later, gate behind a build variant.
**Effort:** included in A1.

### A3. [P0] Duplicate `H3LocationIndex` implementation
**Where:** [feature-core/.../geo/H3LocationIndex.kt](feature-core/src/main/kotlin/com/amanah/feature/core/geo/H3LocationIndex.kt) AND [libraries/location/.../H3LocationIndex.kt](libraries/location/src/main/kotlin/com/amanah/lib/location/H3LocationIndex.kt).
**Issue:** Two implementations of the same class will silently diverge.
**Fix:** Keep `libraries/location/` (it's where geo primitives belong), delete `feature-core/geo/`, update callers.
**Effort:** 0.5 d.

### A4. [P1] Hard-coded sample data in production code path
**Where:**
- [feature-user/.../UserFeature.kt:152-162](feature-user/src/main/kotlin/com/amanah/feature/user/mvi/UserFeature.kt#L152-L162) — `Aisha`, `Omar`
- [feature-admin/.../AdminFeature.kt:81-94](feature-admin/src/main/kotlin/com/amanah/feature/admin/mvi/AdminFeature.kt#L81-L94) — stub user list + stub alert
- [feature-auth/.../LoginFeature.kt:155-158](feature-auth/src/main/kotlin/com/amanah/feature/auth/mvi/LoginFeature.kt#L155-L158) — default `authenticate` returns `Failure(UNKNOWN)`
- [feature-emergency/.../EmergencyAlertEngine.kt:122](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/UserDashboardInteractor.kt#L122) — H3 cell hard-coded to `"872bedfd5ffffff"`
**Issue:** Would ship to release builds.
**Fix:** Move into `app/src/debug/kotlin/.../debug/DebugFixtures.kt`, gate on `BuildConfig.DEBUG`, or hide behind a DI-provided `DemoModeProvider`.
**Effort:** 0.5 d.

### A5. [P3] `typealias LoginEvent = LoginWish` workaround
**Where:** [feature-auth/.../LoginView.kt:54-61](feature-auth/src/main/kotlin/com/amanah/feature/auth/node/login/LoginView.kt#L54-L61).
**Issue:** Comment "so the interactor can use the standard event naming" — a typealias on top of a wish type is a code-smell; just use one or the other consistently across all features.
**Fix:** Pick one (`Wish` everywhere or `Event` everywhere) and rename.
**Effort:** 0.5 d (across all features).

### A6. [P2] String-compare against enum
**Where:** [feature-auth/.../LoginFeature.kt:142-145](feature-auth/src/main/kotlin/com/amanah/feature/auth/mvi/LoginFeature.kt#L142-L145).
```kotlin
effect is LoginEffect.LoginSucceeded && effect.user.role.name == "ADMIN" ->
```
**Issue:** Comparing enum name strings instead of `UserRole.ADMIN`. Fragile if enum is renamed.
**Fix:** `effect.user.role == UserRole.ADMIN`.
**Effort:** 0.1 d.

### A7. [P2] Wrong icon in dark-mode toggle
**Where:** [feature-user/.../UserDashboardView.kt:137-139](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/UserDashboardView.kt#L137-L139).
```kotlin
if (state.isDarkMode) Icons.Default.Settings else Icons.Default.Settings
```
**Issue:** Both branches return the same icon — copy-paste bug. Should be `DarkMode` / `LightMode` (already used correctly in [DashboardView.kt:164-165](feature-core/src/main/kotlin/com/amanah/feature/core/node/dashboard/DashboardView.kt#L164-L165)).
**Effort:** 0.05 d.

---

## B. Missing Foundations

### B1. [P0] No DI graph
**Where:** Dagger 2.52 listed in [MODULE.bazel](MODULE.bazel) but no `AppComponent` exists.
**Issue:** Every feature ends up constructing its own dependencies inline; impossible to swap in test doubles.
**Fix:** Create `app/di/AppComponent.kt` with at minimum: `OkHttpClient`, `Retrofit`, `ApiService`, `Scarlet`, `AmanahWebSocketService`, `TokenStore`, `SessionManager`, `LocationProvider`, `FcmHandler`, `GlobalSnackbarBus`.
**Effort:** 1.0 d.

### B2. [P0] No HTTP client constructed
**Where:** Retrofit + OkHttp deps exist; no `ApiService` interface; no client built.
**Fix:** `feature-core/network/ApiService.kt` + `NetworkModule.kt` (Dagger). Include: `AuthInterceptor` (Bearer token), `RefreshInterceptor` (401 → `/auth/refresh`), `LoggingInterceptor` (debug only), 30s timeouts.
**Effort:** 1.5 d.

### B3. [P0] WebSocket factory not used
**Where:** [feature-core/.../websocket/ScarletFactory.kt](feature-core/src/main/kotlin/com/amanah/feature/core/websocket/ScarletFactory.kt) exists but is never called. `AmanahWebSocketService` is never instantiated.
**Fix:** Construct in `WebSocketModule`, expose as singleton.
**Effort:** 0.5 d.

### B4. [P0] Outbound emergency broadcast is no-op
**Where:** [UserDashboardInteractor.kt:122](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/UserDashboardInteractor.kt#L122).
```kotlin
wsPublish = { /* TODO: wire to AmanahWebSocketService.publishEmergencyAlert() */ },
```
**Issue:** Triggering an emergency *does nothing*. The whole UI flow is dead until this is wired.
**Fix:** Inject `AmanahWebSocketService` into the interactor, wire `wsPublish = { msg -> ws.publishEmergencyAlert(msg.toWire()) }`.
**Effort:** 0.5 d.

### B5. [P0] No persistent storage
**Where:** `androidx.security:security-crypto:1.1.0-alpha06` in `MODULE.bazel`, no `EncryptedSharedPreferences` usage anywhere.
**Issue:** Token persistence is impossible. Authenticated state is in-memory only.
**Fix:** Create `TokenStore` (interface + impl using DataStore Preferences + Tink AEAD), persist access + refresh tokens + last user.
**Effort:** 1.0 d.

### B6. [P0] No global snackbar / toast bus
**Where:** `/* wire to global toast */` TODOs in [RootNode.kt:107](app/src/main/kotlin/com/amanah/app/node/RootNode.kt#L107) and [AppNode.kt:50](app/src/main/kotlin/com/amanah/app/node/AppNode.kt#L50).
**Fix:** Create `GlobalSnackbarBus` as a Reaktive `PublishSubject<SnackbarMessage>`; `AmanahScaffold` subscribes via `LaunchedEffect`.
**Effort:** 0.5 d.

### B7. [P1] No back-stack in Nodes framework
**Where:** [libraries/nodes-framework/](libraries/nodes-framework/).
**Issue:** Android system Back button has no defined behaviour for non-root nodes.
**Fix:** Add `BackStack<T>` class with `push/pop/peek/replace`. Hook into `OnBackPressedDispatcher`.
**Effort:** 1.5 d.

### B8. [P1] No reusable UI primitives
**Where:** Every `*View.kt` re-implements Scaffold + TopAppBar + loading + error + empty inline.
**Fix:** Build the 10 widgets listed in [UI_UX_MVP_PLAN.md §3.2](UI_UX_MVP_PLAN.md).
**Effort:** 1.5 d.

### B9. [P1] No FCM
**Fix:** Vendor `google-services.json`, add Firebase Cloud Messaging dep, build `FcmHandler` with: token refresh listener → POST `/users/devices`, message router → `GlobalEmergencyBus`.
**Effort:** 1.5 d.

### B10. [P1] No foreground service for emergency
**Issue:** Manifest declares `FOREGROUND_SERVICE_LOCATION` but no `Service` class exists. Active emergencies will be killed when the app backgrounds.
**Fix:** `feature-emergency/src/main/.../service/EmergencyForegroundService.kt` with a persistent notification while phase != IDLE.
**Effort:** 1.5 d.

---

## C. Security Findings

### C1. [P0] No certificate pinning
**Where:** OkHttp client (when built) has no `CertificatePinner`.
**Threat:** MITM against `Authorization: Bearer <jwt>` and live location updates.
**Fix:** Pin against the production cert SPKI hash and a backup; rotate via remote-config.
**Effort:** 1.0 d (incl. ops process).

### C2. [P0] `androidx.security:security-crypto` is alpha & deprecated
**Where:** [MODULE.bazel:98](MODULE.bazel#L98) — `1.1.0-alpha06`.
**Issue:** Google has deprecated Jetpack Security. The library will not receive security fixes.
**Fix:** Use Tink directly for AEAD + the Android Keystore for key wrapping. Migrate `TokenStore` to Tink-backed.
**Effort:** 1.0 d.

### C3. [P0] JWT-validation gap
**Issue:** No client-side JWT expiry check before sending each request.
**Fix:** Pre-flight check `exp` claim, kick refresh proactively at 60s before expiry.
**Effort:** 0.5 d.

### C4. [P0] Refresh-token rotation flow missing
**Issue:** Server has `/auth/refresh`; client doesn't call it.
**Fix:** `RefreshInterceptor` on 401, single-flight (mutex) so concurrent requests don't trigger N refreshes.
**Effort:** 1.0 d.

### C5. [P1] Google Maps API key handling
**Where:** [AndroidManifest.xml:31-33](app/src/main/AndroidManifest.xml#L31-L33) — `${MAPS_API_KEY}` placeholder.
**Issue:** Build needs an injection mechanism (Bazel `manifest_values` or CI env); if forgotten the key is `null` and the map silently fails. Also need API restriction: package name + SHA-1.
**Fix:** Wire `--define=MAPS_API_KEY=<key>` flag in Bazel; document in `scripts/secrets/`.
**Effort:** 0.5 d.

### C6. [P1] No request signing or replay protection
**Issue:** Emergency-trigger requests can be replayed within JWT validity window.
**Fix:** Add `X-Request-Id` (UUID v4) on client; server deduplicates within 60s window.
**Effort:** 1.0 d (server + client).

### C7. [P1] No biometric guard for emergency / sensitive actions
**Issue:** Anyone with the unlocked phone can trigger SOS or, more critically, Cancel an active emergency.
**Fix:** Optional biometric prompt before Cancel (preference-controlled).
**Effort:** 0.5 d.

### C8. [P1] Backend rate-limiting incomplete
**Where:** amanah18 has `RateLimitError` exception class but no middleware visible in `main.py`.
**Threat:** Login/OTP/password-reset brute-force.
**Fix:** Add `slowapi` middleware with per-IP and per-account limits; back with Redis.
**Effort:** 1.0 d (backend).

### C9. [P1] WebSocket auth uses query-string token
**Where:** [amanah18 backend/app/websocket.py:215-225](#) — `token = websocket.query_params.get("token")`.
**Issue:** URL tokens are logged by intermediaries (LBs, proxies).
**Fix:** Move token to `Sec-WebSocket-Protocol` header or first-message handshake.
**Effort:** 0.5 d (backend) + 0.5 d (client).

### C10. [P2] No SBOM / dependency scanning
**Fix:** Add Trivy + Snyk + osv-scanner to CI. Fail on CVSS ≥ 7.0.
**Effort:** 1.0 d.

### C11. [P2] Secrets management is `.env` only (amanah18)
**Fix:** Move to HashiCorp Vault / cloud KMS for prod; keep `.env` for local dev.
**Effort:** 2.0 d.

### C12. [P2] No DPIA / privacy impact assessment
**Issue:** App handles real-time location, encrypted PII, audit logs — EU/UK launch requires a DPIA.
**Fix:** Commission a DPIA before EU launch.
**Effort:** External consultant; ~3 weeks calendar.

### C13. [P3] EmergencyButton has no spoof protection
**Issue:** A1's "long-press 1.5s" affordance is fine UX but no protection against shake-detection or notification-area widgets dispatching SOS programmatically (future risk).
**Fix:** Document in security spec.
**Effort:** documentation only.

---

## D. Scalability & Reliability Concerns

### D1. [P0] Single-instance WebSocket in amanah18
**Where:** `app/websocket.py` `ConnectionManager` keeps `user_connections` in a Python `dict`.
**Issue:** A second backend instance cannot route a push to the first instance's connections.
**Fix:** Replace in-process dict with Redis pub/sub + per-instance subscription on its own channel; messages addressed to user_id are published to a channel each instance is subscribed to.
**Effort:** 2.0 d.

### D2. [P1] No connection lifecycle on Android side
**Where:** [AmanahConnectionStateMachine.kt](feature-core/src/main/kotlin/com/amanah/feature/core/websocket/AmanahConnectionStateMachine.kt) defines the FSM but no runtime drives it.
**Issue:** No reconnection backoff, no offline queue, no online/offline UI affordance.
**Fix:** Wire the FSM into a `WebSocketController` singleton owning the Scarlet service. Exponential backoff: 1s → 2s → 5s → 30s → 60s. Persist outgoing emergency messages until ACKed.
**Effort:** 2.0 d.

### D3. [P1] PostgreSQL spatial-query indexing not verified
**Where:** [amanah18 backend/app/db/models/incident.py:115-122](#) has indices on `organization_id`, `region_id`, `status`, etc.
**Issue:** No GiST/SP-GiST indexes for `EmergencyLocation` spatial fields. Nearby-incidents queries will table-scan.
**Fix:** `CREATE INDEX ... USING GIST (location)` in migrations; verify with `EXPLAIN ANALYZE`.
**Effort:** 0.5 d.

### D4. [P1] No connection pooling guardrails
**Issue:** asyncpg/SQLAlchemy default pool size may not survive a traffic spike; no PgBouncer in front.
**Fix:** PgBouncer in transaction-pooling mode; tune pool size = 2 × CPU per backend instance.
**Effort:** 1.0 d.

### D5. [P1] Redis is the SPOF for caching, rate-limiting, Celery, and pub/sub
**Issue:** Single Redis = single point of failure for four critical subsystems.
**Fix:** Redis Sentinel or managed Redis (ElastiCache, MemoryStore).
**Effort:** 1.0 d (ops).

### D6. [P2] No load-test baseline
**Fix:** k6 scripts hitting `/auth/login`, `/incidents/sos`, `/ws` (10K concurrent), `/incidents/{id}/location` at 1 Hz. Run weekly in CI on staging.
**Effort:** 2.0 d.

### D7. [P2] No graceful shutdown for WS
**Issue:** Rolling deploys will hard-close emergency-active WS connections.
**Fix:** SIGTERM handler that broadcasts "reconnect-please" message and lets clients reconnect to a new instance with their incident_id state intact.
**Effort:** 1.0 d.

### D8. [P2] No CDN for static assets
**Fix:** CloudFront / Cloudflare in front of admin panel + asset bucket.
**Effort:** 0.5 d.

### D9. [P3] H3 resolution choices not benchmarked
**Where:** [H3Resolution](libraries/location/src/main/kotlin/com/amanah/lib/location/H3Resolution.kt) defines `DISTRICT` (res 7, ~5km²) and `BLOCK` (res 9, ~0.1km²).
**Issue:** Choice is reasonable but never measured against urban Bangladesh density (the assumed launch market).
**Fix:** Benchmark dispatch latency and false-positive rate at different resolutions in a smoke test with seeded population data.
**Effort:** 1.0 d.

---

## E. Code Quality Findings

### E1. [P1] No tests anywhere
**Where:** All Kotlin modules. `MockK` is in `MODULE.bazel:103` but unused.
**Fix:** Start with `EmergencyFeature` (logic-heavy, easy to test), `LocationPrivacyFilter` (pure math), `ProximityMatcher` (pure logic). Target ≥ 60% coverage on `feature-emergency` and `libraries/location` before MVP.
**Effort:** 2.0 d initial; ongoing.

### E2. [P1] No lint / formatter
**Fix:** Wire `ktlint` + `detekt` into `bazel run //:ktlint`. Add `compose-rules` detekt rules. Fail CI on issues.
**Effort:** 0.5 d.

### E3. [P1] No CI
**Fix:** GitHub Actions: PR pipeline (build + test + lint), main branch (deploy to staging).
**Effort:** 1.0 d.

### E4. [P2] Imports are sprawling
**Where:** Every `*View.kt` has 30-50 Compose imports.
**Fix:** Optional `compose-bom` star import where reasonable; rely on IDE optimisation; no manual fixup required.

### E5. [P2] Magic numbers in UI
**Examples:** [LoginView.kt:182](feature-auth/src/main/kotlin/com/amanah/feature/auth/node/login/LoginView.kt#L182) `.height(52.dp)`, [SplashView.kt:78](feature-core/src/main/kotlin/com/amanah/feature/core/node/splash/SplashView.kt#L78) `delay(800)`, [ResponderMapView.kt:49-56](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/ResponderMapView.kt#L49-L56).
**Fix:** Hoist to `AmanahSpacing` / `AmanahMotion` / `AmanahTouch` constants.
**Effort:** 1.0 d.

### E6. [P2] Mutable lambda interface in NodeView
**Where:** [libraries/nodes-framework/.../NodeView.kt](libraries/nodes-framework/src/main/kotlin/com/amanah/lib/nodes/NodeView.kt) — `var events: ((Event) -> Unit)?`.
**Fix:** Replace with a Reaktive `PublishSubject<Event>` exposed as `Observable<Event>`. Removes the null-check and the lifecycle race when the View is detached mid-emit.
**Effort:** 1.0 d (cross-cutting refactor).

### E7. [P3] `BuildConfig.DEBUG` usage
**Where:** [AmanahApplication.kt:12](app/src/main/kotlin/com/amanah/app/AmanahApplication.kt#L12).
**Issue:** `BuildConfig` is generated by AGP/`kt_android_library` only if explicitly enabled. Verify.
**Fix:** Pin with `kt_android_library(... generate_buildconfig = True)` or use a `DebugFlag` interface from DI.
**Effort:** 0.25 d.

### E8. [P3] Java-isms scattered
**Where:** `java.util.UUID.randomUUID().toString()`, `java.text.SimpleDateFormat`, `System.currentTimeMillis()`.
**Fix:** Wrap with `Clock` (testable) + `IdGenerator` (testable). Use `kotlinx-datetime`.
**Effort:** 1.0 d.

### E9. [P3] `Schedulers.io()` not used
**Where:** Reaktive subscriptions all run on caller thread.
**Issue:** MVICore documents pushing state on the main scheduler; the Actor side-effect work currently runs synchronously inside the Bootstrapper. Stub work is trivially fast but the network repository work will not be — be ready to switch to `observeOn(mainScheduler)` and `subscribeOn(ioScheduler)`.
**Fix:** Document scheduler discipline in `CONTRIBUTING.md`; enforce via lint rule (`reaktive-rules`).
**Effort:** 0.5 d documentation; ongoing discipline.

### E10. [P3] No ProGuard / R8 keep rules
**Where:** No `proguard-rules.pro`.
**Fix:** Add keep rules for: Scarlet `@Send`/`@Receive` annotated methods, Gson `@SerializedName` data classes, Reaktive interfaces, Dagger generated code.
**Effort:** 0.5 d.

---

## F. Observability Gaps

### F1. [P1] No client crash reporting
**Fix:** Sentry SDK; tag `userId`, `release`, `environment`, `node` (current screen).
**Effort:** 0.5 d.

### F2. [P1] No client metrics
**Fix:** Sentry Performance or Firebase Performance. Track: app cold start, screen render time, WS connect/disconnect cadence, emergency-trigger-to-ack latency.
**Effort:** 1.0 d.

### F3. [P1] Backend has structlog but no log shipping
**Fix:** Stdout → Promtail → Loki → Grafana, with `request_id` as a label.
**Effort:** 1.0 d.

### F4. [P1] No business metrics
**Fix:** Prometheus exporters: alerts-per-minute, alerts-acknowledged, alert-to-arrival p50/p95, false-positive cancel rate, MAU.
**Effort:** 1.5 d.

### F5. [P2] No alerting on SLOs
**Fix:** SLOs:
- 99% of WS connections succeed within 2s.
- 99% of `/incidents/sos` ACKs within 1s.
- 99.9% incident alert delivery within 5s.
Alert on burn-rate (Prometheus AlertManager → PagerDuty).
**Effort:** 2.0 d.

---

## G. Process & Documentation Gaps

### G1. [P1] No README in active project
**Fix:** Top-level `README.md` with setup, build, run, test, deploy. Currently `Amanah_App/` has zero docs (these 5 docs are the start).
**Effort:** 0.5 d.

### G2. [P1] No `CONTRIBUTING.md`
**Fix:** Describe Node pattern, MVI invariants, Compose discipline, threading discipline, security review for PII-touching code.
**Effort:** 0.5 d.

### G3. [P1] No `SECURITY.md`
**Fix:** Disclosure policy + threat model summary.
**Effort:** 0.5 d.

### G4. [P2] No ADRs
**Fix:** `docs/adr/` directory with: ADR-001 Bazel, ADR-002 Nodes framework, ADR-003 H3 spatial index, ADR-004 Backend retain from amanah18, ADR-005 Dagger over Hilt, ADR-006 Scarlet over OkHttp+WebSocketListener, etc.
**Effort:** 1.0 d initial.

### G5. [P2] No API contract testing
**Fix:** Schemathesis (Python) or Pact (Kotlin) consumer-driven contract tests.
**Effort:** 2.0 d.

### G6. [P3] No on-call runbook
**Fix:** Once production: runbook per major service (backend, Redis, Postgres, WS), top-10 incidents with mitigation steps.

---

## H. Quick-fix Punch List (under 1 day total)

These are tiny, independent, and high-signal:

| # | Task | File | Effort |
|---|---|---|---|
| 1 | Fix dark-mode icon copy-paste bug | [UserDashboardView.kt:137](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/UserDashboardView.kt#L137) | 5min |
| 2 | Enum compare instead of string compare | [LoginFeature.kt:142](feature-auth/src/main/kotlin/com/amanah/feature/auth/mvi/LoginFeature.kt#L142) | 5min |
| 3 | Delete `AppNode.kt` | [app/.../node/AppNode.kt](app/src/main/kotlin/com/amanah/app/node/AppNode.kt) | 5min |
| 4 | Delete dead Islamic-dashboard | [feature-core/.../node/dashboard/](feature-core/src/main/kotlin/com/amanah/feature/core/node/dashboard/), [feature-core/.../mvi/DashboardFeature.kt](feature-core/src/main/kotlin/com/amanah/feature/core/mvi/DashboardFeature.kt) | 15min |
| 5 | Delete duplicate H3LocationIndex | [feature-core/.../geo/H3LocationIndex.kt](feature-core/src/main/kotlin/com/amanah/feature/core/geo/H3LocationIndex.kt) | 10min |
| 6 | Move stub users to debug fixtures | [UserFeature.kt:152](feature-user/src/main/kotlin/com/amanah/feature/user/mvi/UserFeature.kt#L152), [AdminFeature.kt:81](feature-admin/src/main/kotlin/com/amanah/feature/admin/mvi/AdminFeature.kt#L81) | 1h |
| 7 | Add `.gitignore` entries for `bazel-*` symlinks if missing | [.gitignore](.gitignore) | 5min |
| 8 | Add top-level `README.md` | `README.md` | 1h |
| 9 | Add `CHANGELOG.md` | `CHANGELOG.md` | 15min |
| 10 | Add `SECURITY.md` skeleton | `SECURITY.md` | 15min |

---

## I. Roll-up by Severity

```
P0  (ship-stopper / demo-blocker)        : 13 items  (≈ 11 eng-days)
P1  (MVP window, must close in 4 weeks)  : 22 items  (≈ 28 eng-days)
P2  (hardening, months 2-3)              : 16 items  (≈ 20 eng-days)
P3  (cleanup, opportunistic)             : 11 items  (≈ 7 eng-days)
                                          ─────────────────────────
                                  TOTAL  : 62 items  (≈ 66 eng-days)
```

**One-line conclusion:** The architecture is sound, but **nothing has been wired together yet**. Most of the debt is "wire X to Y," not "rewrite X." Estimate ≈11 engineer-days to close every P0 — which matches the customer-demo target in [PROJECT_AUDIT_AND_ROADMAP.md §11](PROJECT_AUDIT_AND_ROADMAP.md).
