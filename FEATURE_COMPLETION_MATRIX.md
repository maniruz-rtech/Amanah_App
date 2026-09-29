# Amanah_App — Feature Completion Matrix

Compares feature-level completeness between **amanah18** (legacy reference) and **Amanah_App** (active Bazel/Kotlin rewrite).

**Legend:**
- ✅ — implemented & functional end-to-end
- 🟡 — partial (UI only, or backend only, or stubbed)
- ❌ — not implemented
- 🚫 — explicitly out of scope / not planned

---

## 1. Authentication & Identity

| Feature | amanah18 backend | amanah18 Flutter | amanah18 Admin | Amanah_App |
|---|---|---|---|---|
| Username/password login | ✅ | ✅ | ✅ | 🟡 UI only ([LoginView.kt](feature-auth/src/main/kotlin/com/amanah/feature/auth/node/login/LoginView.kt); `authenticate` stub) |
| JWT access token | ✅ | ✅ | ✅ | ❌ |
| Refresh token rotation | ✅ (`/auth/refresh`) | ✅ | ✅ | ❌ |
| Multi-factor auth (TOTP) | ✅ (`/auth/mfa/setup|confirm|verify`) | ✅ | ✅ | ❌ |
| OTP request/verify (phone/email) | ✅ (`/auth/otp/request`, `/api/v1/otp/*`) | ✅ | — | ❌ |
| Password reset (admin-controlled) | ✅ (`/auth/password-reset/*`) | ✅ | ✅ | 🟡 UI only ([PasswordResetView.kt](feature-auth/src/main/kotlin/com/amanah/feature/auth/node/passwordreset/PasswordResetView.kt)) |
| Logout single | ✅ | ✅ | ✅ | 🟡 navigates but no token revocation |
| Logout all devices | ✅ (`/auth/logout/all`) | ✅ | ✅ | ❌ |
| Argon2id password hashing | ✅ | — | — | n/a (server-side) |
| Account lockout after failed attempts | ✅ (`AccountLockedError`) | ✅ | ✅ | ❌ |
| Pending-approval state | ✅ | ✅ | ✅ | 🟡 UI state defined; never set |
| Suspended-account state | ✅ | ✅ | ✅ | 🟡 UI state defined; never set |
| Biometric login | ❌ | ❌ | — | 🟡 dependency present, no UI |
| Session management UI | ❌ | 🟡 | ❌ | ❌ |

---

## 2. User Profile & Onboarding

| Feature | amanah18 | Amanah_App |
|---|---|---|
| First-launch onboarding (3 screens) | ❌ | ❌ |
| Permission priming (location + notification) | 🟡 (Flutter) | ❌ |
| View profile | ✅ (`/users/me`, `profile_screen.dart`) | 🟡 read-only stub ([UserDashboardView.ProfileTab](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/UserDashboardView.kt#L368)) |
| Edit profile | ✅ (`edit_profile_screen.dart`) | ❌ |
| Avatar upload | 🟡 (`avatar_url` field exists; upload UI partial) | ❌ |
| Encrypted PII at rest | ✅ (`phone_encrypted`, `email_encrypted`, `full_name_encrypted` columns) | n/a (server) |
| Verify phone (OTP) | ✅ (`verify_phone_screen.dart`) | ❌ |
| Verify email (OTP) | ✅ (`verify_email_screen.dart`) | ❌ |
| Display name + username separation | ✅ | 🟡 model exists |
| MFA enrolment from settings | ✅ | ❌ |

---

## 3. Trusted Contacts (port from amanah18)

| Feature | amanah18 | Amanah_App |
|---|---|---|
| List trusted contacts | ✅ (`/users/trusted-contacts`, `trusted_contacts_repository.dart`) | ❌ |
| Add trusted contact | ✅ | ❌ |
| Edit trusted contact | ✅ | ❌ |
| Delete trusted contact | ✅ | ❌ |
| Notify trusted contacts on SOS | ✅ (`Notification` model) | ❌ |

---

## 4. Devices

| Feature | amanah18 | Amanah_App |
|---|---|---|
| Register device on login | ✅ (`/users/devices`, `device_repository.dart`) | ❌ |
| List user devices | ✅ | ❌ |
| Revoke device | ✅ (`DELETE /users/devices/{id}`) | ❌ |
| Push device-info card | ✅ (`device_info_card.dart`) | ❌ |
| Device-token monitor service | ✅ (`device_token_monitor_service.dart`) | ❌ |

---

## 5. SOS / Emergency

| Feature | amanah18 | Amanah_App |
|---|---|---|
| Quick SOS (1-tap) | ✅ (`quick_sos_screen.dart`, `POST /incidents/sos`) | 🟡 long-press button ([UserDashboardView.EmergencyButton](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/UserDashboardView.kt#L256)); not wired to backend |
| Detailed SOS (type + severity + note + location) | ✅ (`detailed_sos_screen.dart`, IncidentType / IncidentSeverity) | ❌ |
| Incident state machine (CREATED→ACTIVE→ASSIGNED→IN_PROGRESS→RESOLVED) | ✅ (`IncidentStatus`) | 🟡 different state machine in [EmergencyFeature.Phase](feature-emergency/src/main/kotlin/com/amanah/feature/emergency/mvi/EmergencyFeature.kt#L45) — need to reconcile semantics |
| Silent SOS (no haptic / no audible feedback) | ✅ (`silent_mode` on Incident) | ❌ |
| Incident cancel (with reason) | ✅ (`POST /incidents/{id}/cancel`) | 🟡 UI button exists; no reason capture |
| Incident resolve (responder action) | ✅ (`POST /incidents/{id}/resolve`) | 🟡 admin "Force Resolve" button exists; no reason capture |
| Incident detail screen | ✅ (`incident_details_screen.dart`) | ❌ |
| Background SOS while phone locked | 🟡 (background isolate in Flutter) | ❌ (no foreground service) |
| Offline SOS queue (durable) | ❌ | ❌ |
| SOS confirmation dialog | ✅ | ✅ (long-press is the confirmation) |
| Privacy: location obfuscation when idle | 🟡 (server-side obfuscation hinted, not enforced) | ✅ (`LocationPrivacyFilter` with Box-Muller noise — better than amanah18) |
| H3 cell indexing | ❌ | ✅ ([H3LocationIndex](libraries/location/src/main/kotlin/com/amanah/lib/location/H3LocationIndex.kt), [ProximityMatcher](feature-emergency/src/main/kotlin/com/amanah/feature/emergency/proximity/ProximityMatcher.kt)) |
| k-ring proximity matching | ❌ (radius-based) | ✅ |

---

## 6. Responders

| Feature | amanah18 | Amanah_App |
|---|---|---|
| Responder availability toggle | ✅ (`ResponderStatus`, `/responders/*`, `responder_availability_repository.dart`) | ❌ |
| Receive incident assignment | ✅ (WS `incident_assigned`) | ❌ |
| Accept assignment | ✅ | 🟡 *received* via `ResponderAccepted` wish; no UI to *send* acceptance |
| Decline assignment | ✅ | ❌ |
| Live location push to incident | ✅ (`POST /incidents/{id}/location` + WS) | 🟡 received via `observeResponderLocations()`; not published outbound |
| ETA estimation | ✅ (`responder_status` + computed) | 🟡 computed client-side from raw distance; server should provide |
| "Arrived" event | ✅ (WS `responder_arrived`) | ❌ |
| Responder dashboard (list of active incidents) | ✅ (`dispatcher_dashboard_screen.dart`, `responder_actions_repository.dart`) | ❌ |
| Responder incident detail | ✅ (`responder_incident_detail_screen.dart`) | ❌ |

---

## 7. Real-time / WebSocket

| Feature | amanah18 | Amanah_App |
|---|---|---|
| WebSocket endpoint | ✅ (`/ws?token=<JWT>`, `ConnectionManager`) | 🟡 service interface ([AmanahWebSocketService.kt](feature-core/src/main/kotlin/com/amanah/feature/core/websocket/AmanahWebSocketService.kt)) — factory not instantiated |
| JWT auth on WS | ✅ | ❌ (interceptor not built) |
| Subscribe to incident updates | ✅ | ❌ |
| location_update broadcast | ✅ | 🟡 wire type defined, no consumer wired |
| status_update broadcast | ✅ | ❌ |
| responder_accepted message | ✅ | 🟡 wire type defined |
| responder_arrived message | ✅ | ❌ |
| incident_assigned (push to responder) | ✅ | ❌ |
| Per-user connection pool | ✅ | ❌ |
| Multi-instance via Redis pub/sub | ❌ | ❌ |
| Auto-reconnect | ❌ (client) | 🟡 ([AmanahConnectionStateMachine](feature-core/src/main/kotlin/com/amanah/feature/core/websocket/AmanahConnectionStateMachine.kt) exists; not wired into a runtime) |
| Heartbeat / presence | ❌ | 🟡 `publishPresence()` defined; no caller |
| Connectivity banner in UI | 🟡 (Flutter) | ❌ |

---

## 8. Notifications & Push

| Feature | amanah18 | Amanah_App |
|---|---|---|
| Notification list endpoint | ✅ (`/notifications`) | ❌ |
| Unread badge count | ✅ (`/notifications/unread-count`) | ❌ |
| Mark-as-read | ✅ | ❌ |
| Mark-all-as-read | ✅ | ❌ |
| Notification center screen | ✅ (`NotificationCenterPage.tsx`, `notifications_repository.dart`) | ❌ |
| FCM device token registration | ✅ (`firebase_fcm_service.dart`, `device_token_monitor_service.dart`) | ❌ |
| Foreground notification handling | ✅ | ❌ |
| Background notification handling | ✅ | ❌ |
| Notification preferences | 🟡 partial | ❌ |
| In-app toast/snackbar bus | 🟡 (Flutter) | ❌ (`/* wire to global toast */` TODO) |

---

## 9. Admin Console

| Feature | amanah18 React admin | Amanah_App `feature-admin` |
|---|---|---|
| Login | ✅ `LoginPage.tsx` | ✅ shared login |
| Dashboard | ✅ `DashboardPage.tsx` | 🟡 ([AdminDashboardView](feature-admin/src/main/kotlin/com/amanah/feature/admin/node/dashboard/AdminDashboardView.kt)) |
| User list + search | ✅ `UserListPage.tsx` | 🟡 stub data |
| User detail | ✅ `UserDetailsPage.tsx` | ❌ |
| User create | ✅ `UserCreatePage.tsx` | ❌ |
| User edit | ✅ | ❌ (`/* TODO: attach EditUserNode */`) |
| Approve user | ✅ | 🟡 button wired to MVI; no backend call |
| Suspend user | ✅ | 🟡 button wired to MVI; no backend call |
| Approvals queue | ✅ `ApprovalsPage.tsx` | ❌ (only a badge count) |
| Audit log viewer | ✅ `AuditLogsPage.tsx` | ❌ |
| Incident list | ✅ `IncidentListPage.tsx` | 🟡 in `AlertsTab` |
| Incident detail | ✅ `IncidentDetailsPage.tsx` | ❌ |
| Force-resolve incident | ✅ | 🟡 button exists; no backend call |
| Notification center (admin) | ✅ `NotificationCenterPage.tsx` | ❌ |
| Organisations list | ✅ `OrganizationListPage.tsx` | ❌ |
| Regions list | ✅ `RegionListPage.tsx` | ❌ |
| Roles list | ✅ `RoleListPage.tsx` | ❌ |
| Role detail / permissions | ✅ `RoleDetailsPage.tsx` | ❌ |
| Admin settings | ✅ `SettingsPage.tsx` | ❌ |
| Stats (counts) | ❌ | ✅ ([StatsTab](feature-admin/src/main/kotlin/com/amanah/feature/admin/node/dashboard/AdminDashboardView.kt#L333)) |
| Live alert feed via WS | ❌ | 🟡 `LiveAlertReceived` effect defined; no producer |

---

## 10. Multi-tenant / Org / Region

| Feature | amanah18 | Amanah_App |
|---|---|---|
| Organisation entity | ✅ `Organization` model | ❌ |
| Region entity | ✅ `Region` model | ❌ |
| Org-scoped queries (every list filtered by org) | ✅ | ❌ |
| Region-scoped queries | ✅ | ❌ |
| Cross-org isolation | ✅ | ❌ |
| Super-admin role | ✅ (`is_super_admin`) | ❌ (only `UserRole.ADMIN/USER`) |
| Regional admin role | ✅ (`regional_admin`) | ❌ |

---

## 11. Settings & Preferences

| Feature | amanah18 | Amanah_App |
|---|---|---|
| Dark mode toggle | 🟡 | ✅ ([UserDashboardView.SettingsTab](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/UserDashboardView.kt#L392)) |
| Notification preferences | ✅ | ❌ |
| Language | 🟡 partial | ❌ |
| Location precision (high / medium / battery-saver) | ❌ | ❌ |
| About / version / legal | ✅ | ❌ |
| Privacy policy link | ✅ | 🟡 single line of text |
| Logout from settings | ✅ | ✅ (button in ProfileTab) |
| Delete account | ❌ (Flutter) | ❌ |
| Data export | ❌ | ❌ |

---

## 12. Observability & Diagnostics

| Feature | amanah18 | Amanah_App |
|---|---|---|
| Request ID middleware | ✅ | n/a (server) |
| structlog structured logs | ✅ | n/a |
| Sentry / crash reporting | ❌ | ❌ |
| In-app debug drawer | ❌ | ✅ ([AmanahDebugDrawer.kt](feature-core/src/main/kotlin/com/amanah/feature/core/debug/AmanahDebugDrawer.kt)) |
| Prometheus metrics | ❌ | ❌ |
| Grafana dashboards | ❌ | ❌ |
| OpenTelemetry tracing | ❌ | ❌ |
| App-side performance traces | ❌ | ❌ |

---

## 13. CI / CD / DevOps

| Item | amanah18 | Amanah_App |
|---|---|---|
| Local dev script | ✅ `setup-dev.sh`, `start-system.sh`, `stop-system.sh` | ❌ |
| Docker-compose | 🟡 partial | ❌ |
| GitHub Actions workflow | ❌ | ❌ |
| Lint / format CI | ❌ | ❌ |
| Test CI | ❌ | ❌ |
| Container registry push | ❌ | ❌ |
| Staging environment | ❌ | ❌ |
| Production environment | ❌ | ❌ |
| Alembic migrations runner in CI | ❌ | ❌ |
| Bazel remote cache | ❌ | 🟡 `bazel_diff.sh` placeholder |
| APK signing / Play Store config | n/a | ❌ |

---

## 14. Tests

| Type | amanah18 | Amanah_App |
|---|---|---|
| Backend unit tests | 🟡 `backend/tests/unit/` directory present | n/a |
| Backend integration tests | 🟡 `backend/tests/integration/` present | n/a |
| Backend security tests | 🟡 `backend/tests/security/` present | n/a |
| Flutter widget tests | 🟡 `flutter_app/test/` minimal | n/a |
| Kotlin unit tests | n/a | ❌ |
| Kotlin instrumentation tests | n/a | ❌ |
| Compose UI tests | n/a | ❌ |
| E2E / contract tests | ❌ | ❌ |
| Load / k6 tests | ❌ | ❌ |
| Security pen-test | ❌ | ❌ |

---

## 15. Privacy / Compliance

| Feature | amanah18 | Amanah_App |
|---|---|---|
| Encrypted PII at rest (phone/email/name) | ✅ | n/a (server) |
| Location auto-expiry post-incident | 🟡 (`90 days` documented in CLAUDE.md, enforcement unclear) | n/a |
| Audit log retention 24 months | 🟡 documented | n/a |
| Privacy policy hosted | ❌ | ❌ |
| ToS hosted | ❌ | ❌ |
| GDPR data export (Article 15) | ❌ | ❌ |
| GDPR deletion (Article 17) | ❌ | ❌ |
| DPIA performed | ❌ | ❌ |
| Location obfuscation (idle) | 🟡 hinted | ✅ ([LocationPrivacyFilter.obfuscate](libraries/location/src/main/kotlin/com/amanah/lib/location/LocationPrivacyFilter.kt#L60)) |
| Distance rounding (anti-trilateration) | ❌ | ✅ ([roundToNearest100m](libraries/location/src/main/kotlin/com/amanah/lib/location/LocationPrivacyFilter.kt#L94)) |
| Exact GPS only during ACTIVE_EMERGENCY | 🟡 server policy | ✅ enforced at client multiple points |

---

## 16. Summary Counts

```
Total feature rows surveyed: ~145

amanah18 implementation status:
  ✅  fully working                 : ~92
  🟡  partial / not in all surfaces : ~32
  ❌  not implemented               : ~21

Amanah_App implementation status:
  ✅  fully working                 : ~9   (mostly: privacy filters, H3, theme tokens, splash, design of MVI pipelines)
  🟡  partial / stubbed             : ~28
  ❌  not implemented               : ~108
```

**Headline:** Amanah_App's *architecture-and-design* completion is high (≈70%). Its *feature implementation* completion is low (≈12%). The gap is the work ahead.

---

## 17. Top 20 Features to Implement First (priority order)

1. **DI graph + ApiService + WebSocket factory + TokenStore** — unlocks every wire below.
2. **Backend redeploy from amanah18** — unblocks all integration.
3. **Login → real backend** — first ✅ end-to-end flow.
4. **Onboarding (3) + permission priming (2)** — first impression for demo.
5. **User Dashboard → real nearby + WS subscribe** — visible "real" content.
6. **Emergency trigger → real WS publish + backend incident create** — proves the headline value.
7. **Live responder map (real WS data)** — already polished UI, just needs data.
8. **ETA card driven by backend** — completes emergency loop.
9. **Alert detail (user)** — drill-down from history.
10. **Admin live alert feed (WS subscribed)** — admin sees the demo alert.
11. **Admin "Approve user" → real `POST /admin/...`** — admin action loop.
12. **Alert detail (admin) + Force Resolve** — closes the demo loop.
13. **FCM registration + receipt** — emergency push delivery.
14. **Logout (real, token revoked) + refresh-token rotation** — session correctness.
15. **Trusted contacts (list + add + delete)** — port from amanah18.
16. **Edit profile + verify phone (OTP)** — minimum profile completeness.
17. **Notification center** — list + mark-read.
18. **Settings (real)** — language, notification prefs, dark mode persistence.
19. **Audit log viewer (admin)** — port from amanah18.
20. **Org / region / role management (admin)** — multi-tenant unlock.
