# Android ↔ Backend Connection Status

Per-feature inventory: does the client really call the backend? Or does it
fabricate data and pretend?

---

## 1. Infrastructure layers (all real)

| Component | File | Status |
|---|---|---|
| Retrofit `ApiService` interface (25+ endpoints) | `feature-core/network/ApiService.kt` | ✅ Complete |
| Retrofit + Gson + OkHttp setup | `feature-core/network/ApiFactory.kt` | ✅ Pinned client + redacted Authorization header |
| `AuthInterceptor` | `feature-core/network/AuthInterceptor.kt` | ✅ Bearer header injection |
| `RefreshInterceptor` (single-flight, retry-once) | `feature-core/network/RefreshInterceptor.kt` | ✅ |
| `CertificatePinner` | `feature-core/network/PinningConfig.kt` | ✅ Primary + backup SPKI |
| `SecureTokenStore` (Tink AEAD + DataStore) | `feature-core/session/TinkTokenStore.kt` | ✅ |
| `SessionManager` (BehaviorSubject) | `feature-core/session/SessionManager.kt` | ✅ |
| `RealtimeGateway` (OkHttp WebSocket, header auth) | `feature-core/realtime/OkHttpRealtimeGateway.kt` | ✅ |
| Process DI graph | `app/di/AppGraph.kt` | ✅ |

**The plumbing is all there.** What's missing is the *user* of the plumbing —
the repositories that translate feature-level concerns into Retrofit calls.

---

## 2. Repositories — what exists and what's missing

### Exists
- `feature-auth/repository/AuthRepository.kt` — login, requestPasswordReset.

### Missing (must be written to wire each feature)
- `feature-user/repository/UserRepository.kt` — getMe, updateMe, listNearbyActive, listAlertHistory, getAlert
- `feature-user/repository/TrustedContactsRepository.kt`
- `feature-user/repository/DeviceRepository.kt`
- `feature-emergency/repository/EmergencyRepository.kt` — createSos (REST POST), pushLocation, cancel, resolve
- `feature-admin/repository/AdminRepository.kt` — listUsers, getUser, approve, suspend, listAlerts, getAlert, resolveIncident, listAuditLogs, listApprovals, approveApproval
- `feature-core/repository/NotificationsRepository.kt` — list, markRead, markAllRead, unreadCount
- `feature-auth/repository/OtpRepository.kt` — request, verify, resend
- `feature-core/repository/PresenceRepository.kt` — periodic UPDATE of user's last H3 cell (via REST or WS)

---

## 3. Feature-by-feature connection status

### feature-auth

| Path | Backend call? | Stub? |
|---|---|---|
| Login screen → `LoginFeature.Submit` | ✅ → `POST /api/v1/auth/login` | No |
| Password reset request | ❌ — UI only | Yes — there is no `AuthRepository.requestPasswordReset()` call wired |
| Onboarding | n/a — local-only flow | No |

Action: wire `PasswordResetView` submit to `AuthRepository.requestPasswordReset(...)`.

### feature-user

| Path | Backend call? | Stub? |
|---|---|---|
| Splash → fetch session user (`/users/me`) | ❌ — `RootNode` doesn't load a session from disk | The `AuthenticatedUser` is taken from the login response only |
| Home tab nearby grid | ❌ | `UserFeature.loadNearbyUsers` hard-codes "Aisha, Omar" |
| Home tab → `RefreshNearby` | ❌ | Same |
| Emergency button → outbound | ⚠️ Calls `RealtimeGateway.send(EMERGENCY_ALERT envelope)` over WS. Backend WS handler is a TODO. **No DB row created.** | n/a |
| Alerts tab — history | ❌ | Empty list (state default) |
| Alert card → Incident detail | ❌ | `IncidentDetailInteractor` fabricates fixture |
| Profile tab — read | ❌ | Renders from `state.currentUser`, never re-fetched from `/users/me` |
| Profile tab — edit | ❌ | Not wired |
| Logout | ✅ — clears tokens, disconnects gateway | No (but no `/auth/logout` POST yet) |
| Trusted contacts | ❌ | Screen not built |
| Verify phone (OTP) | ❌ | Screen not built |
| Verify email (OTP) | ❌ | Screen not built |
| Device registration (FCM) | ❌ | No FCM yet |

### feature-admin

| Path | Backend call? | Stub? |
|---|---|---|
| Admin dashboard load (`Bootstrapper { LoadAll }`) | ❌ | `AdminActor.LoadAll` produces a hard-coded `stubUsers` + `stubAlerts` |
| Search users | ⚠️ | Filters in-memory; never calls `?q=` |
| User card approve / suspend / edit | ⚠️ | MVI mutation only; no `POST /admin/users/{id}/approve` |
| User detail node | ❌ | `AdminUserDetailInteractor` fabricates identity, devices, activity |
| Alert detail node | ❌ | `AdminAlertDetailInteractor` fabricates victim + responders |
| Alert force-resolve | ❌ | MVI mutation only; no `POST /incidents/{id}/resolve` |
| Stats tab | ⚠️ | Counts derived from the same stub data |
| Live alert feed (WS) | ⚠️ | `LiveAlertReceived` effect defined; never emitted (no producer) |
| Audit log viewer | ❌ | Not built |
| Approvals queue | ❌ | Not built (only the badge count is wired) |

### feature-emergency

| Path | Backend call? | Stub? |
|---|---|---|
| `EmergencyAlertEngine.triggerAlert(lat, lng)` | ⚠️ | Calls `feature.accept(TriggerAlert)` → reducer flips phase → news `BroadcastEmergency` → `wsPublish(...)` → gateway sends WS envelope. No REST INSERT. |
| `EmergencyAlertEngine.cancelAlert()` | ⚠️ | Same WS path; no REST `POST /incidents/{id}/cancel` |
| Receiving incoming emergency from server | ⚠️ | Subscribes to `gateway.incoming`. Works for WS-delivered alerts. |
| Receiving responder location during ACTIVE | ⚠️ | Same. |
| `currentUserH3Cell` | ❌ — hard-coded `"872bedfd5ffffff"` | Need `LocationProvider` |

### feature-core

| Path | Backend call? | Stub? |
|---|---|---|
| WebSocket connect after login | ✅ — `RootNode.showUserDashboard` calls `graph.realtimeGateway.connect()` | No |
| Heartbeat ping/pong | ✅ — `HeartbeatScheduler` running | No |
| Auth header on WS handshake | ✅ — `OkHttpRealtimeGateway.doOpen` reads token from `tokenProvider.current()` and adds `Authorization` header | No |
| Refresh on 401 | ✅ — `RefreshInterceptor` | But: WS 401 → `Terminated(AUTH_REJECTED)` — gateway does NOT trigger a refresh. **Bug — see implementation steps.** |

---

## 4. Critical client-side gaps

In rough order of demo / production blast radius:

1. **SOS doesn't persist** (highest impact). The Android button → WS envelope path doesn't persist on the backend. Need to switch the trigger path to `POST /api/v1/incidents/sos` (which IS persisted), then use WS for inbound fanout only.
2. **No `UserRepository`** — Home tab is fake.
3. **No `AdminRepository`** — Admin dashboard is fake.
4. **No `EmergencyRepository`** — incident lifecycle has no REST anchor.
5. **No incident-detail load** — drill-down screens fabricate data.
6. **No session rehydration on cold start** — `RootNode` always starts at Splash → Login. A returning user with a valid token still has to log in again. (Token IS persisted; nothing reads it on startup.)
7. **No `LocationProvider`** — H3 cell hard-coded.
8. **WS 401 doesn't trigger refresh** — gateway terminates instead of refreshing.

---

## 5. Quick wins (each ≤ 2 hours)

These give visible signs of life with minimal effort:

| Win | File | What |
|---|---|---|
| Real `/users/me` after login | `feature-user/repository/UserRepository.kt` (new) | Single call; populate ProfileTab |
| Real alert history | `UserRepository.listMyActiveIncidents` calling `/incidents/my/active` | Replace empty state with actual incidents |
| Real admin user list | `AdminRepository.listUsers` calling `/admin/users` | Replace stub |
| Real `POST /admin/users/{id}/approve` from AdminUserDetail | `AdminRepository.approveUser` | Replace MVI-only mutation |
| Session rehydration on startup | `RootNode.onAttach` checks `graph.tokenStore.hasSession()` and routes accordingly | Returning-user UX |

---

## 6. What "connected" should look like

```
LoginNode
  │
  │ AuthRepository.login()
  ▼
ApiService.login()  ── HTTPS, header auth, pinned ──►  POST /auth/login
                                                       │
                                                       ▼
                                                  UserRepository.find_by_…
                                                       │
                                                       ▼
                                                  asyncpg + Postgres
                                                       │
                                            ◄──────────┘   row + JWT
SessionManager.signIn(...)                                  │
TinkTokenStore.save(access, refresh)                       │
graph.realtimeGateway.connect()                            │
  │                                                        │
  │ Authorization: Bearer …                                │
  ▼                                                        │
WSS /ws  ◄─────────────────────────────────────────────────┘
  │     ◄── inbound: emergency.alert (broadcast from /incidents/sos)
  │     ◄── inbound: responder.location (broadcast from /incidents/{id}/location)
  │
  ▼ RealtimeGateway.incoming
EmergencyAlertEngine.onIncomingAlert  /  onResponderLocationUpdate
  │
  ▼
UserFeature state — real
```

The plumbing is there. We just need to actually hook the features to it.
