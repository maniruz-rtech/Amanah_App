# Amanah_App — UI / UX MVP Plan

**Goal:** A customer-demoable, production-grade UI in the shortest credible time. This document is screen-by-screen, with priorities, dependencies, and effort.

---

## 1. Current UI Maturity Snapshot

| Screen | File | LOC | UI Quality | Functional? |
|---|---|---|---|---|
| Splash | [feature-core/.../node/splash/SplashView.kt](feature-core/src/main/kotlin/com/amanah/feature/core/node/splash/SplashView.kt) | 124 | ★★★★☆ animated, branded | ✅ |
| Login | [feature-auth/.../node/login/LoginView.kt](feature-auth/src/main/kotlin/com/amanah/feature/auth/node/login/LoginView.kt) | 249 | ★★★★☆ polished | ⚠️ stub |
| Password Reset | [feature-auth/.../node/passwordreset/PasswordResetView.kt](feature-auth/src/main/kotlin/com/amanah/feature/auth/node/passwordreset/PasswordResetView.kt) | 133 | ★★★☆☆ minimal | ⚠️ stub |
| Generic Dashboard *(dead)* | [feature-core/.../node/dashboard/DashboardView.kt](feature-core/src/main/kotlin/com/amanah/feature/core/node/dashboard/DashboardView.kt) | 256 | ★★★☆☆ | ⚠️ Islamic-modules dead path |
| User Dashboard | [feature-user/.../node/dashboard/UserDashboardView.kt](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/UserDashboardView.kt) | 535 | ★★★★☆ tabs+pulse button | ⚠️ stub |
| Emergency Map | [feature-user/.../node/dashboard/ResponderMapView.kt](feature-user/src/main/kotlin/com/amanah/feature/user/node/dashboard/ResponderMapView.kt) | 298 | ★★★★★ best screen | ⚠️ no live data |
| Admin Dashboard | [feature-admin/.../node/dashboard/AdminDashboardView.kt](feature-admin/src/main/kotlin/com/amanah/feature/admin/node/dashboard/AdminDashboardView.kt) | (≈350) | ★★★★☆ tabs + cards | ⚠️ stub |

**Total UI surface:** ~8 screens, of which **only 6 are reachable** by the live `RootNode`. None are end-to-end functional.

---

## 2. UI Maturity Issues

### 2.1 Identity confusion
- `DashboardFeature.kt` defines modules **Prayer Times / Quran / Zakat / Calendar / Qibla**.
- `RootNode` routes to a **Login → Emergency Dashboard** flow.
- These are two different products in one codebase. The customer demo cannot be ambiguous about whether Amanah is "Muslim productivity" or "community safety SOS." **Resolve identity = community safety SOS for verified members.** Delete Islamic modules from core; if they return, they go behind a feature flag in a separate module.

### 2.2 No design system
- 4 different colors for "primary action" appear across screens.
- Padding is hand-coded as raw `dp` (e.g. `16.dp`, `12.dp`, `24.dp`, `8.dp`).
- 3 different button shapes are used.
- Snackbar shows up sometimes; toast hooks exist but are unwired (`/* wire to global toast */`).

### 2.3 No reusable widgets
- Every `*View.kt` has its own `Scaffold` + `TopAppBar` + `SnackbarHost` + loading + error state.
- amanah18 had `core/widgets/app_loading.dart`, `app_empty.dart`, `app_error.dart`. We need the Kotlin equivalents.

### 2.4 No empty / loading / error consistency
- `UserDashboardView.HomeTab` uses `CircularProgressIndicator` directly.
- `AdminDashboardView` uses `CircularProgressIndicator` directly.
- `LoginView` shows a tiny spinner inside the Button.
- `DashboardView.LoadingPanel` is one inconsistent variant.

### 2.5 Map UX is the gold standard
- `ResponderMapView` is the model: WeakHandler camera fly-to, key-based marker pooling, privacy-rounded distances, haptic feedback, ETA-coloured markers, calibrating spinner when ETA unknown.
- Bring other screens up to this fidelity, or step them down so the demo flow feels consistent (the latter is faster).

### 2.6 No first-launch experience
- App opens → Splash → Login.
- No onboarding, no permission priming, no role chooser explanation.

### 2.7 No navigation back-stack
- `Node` framework has no `BackStack`.
- Android system Back button currently has no defined behaviour for non-root nodes (PasswordReset, future IncidentDetail).
- `MainActivity` doesn't override `onBackPressed()` (and shouldn't — but the nodes need to react).

### 2.8 No accessibility pass
- EmergencyButton's content description is missing on the inner Icon, present on the parent Text.
- `FilledIconToggleButton` for dark-mode uses `Icons.Default.Settings` in both branches — wrong icon.
- Font scale 200% has not been tested.
- 48dp minimum touch target has not been audited.

### 2.9 No RTL test
- `supportsRtl="true"` is in the manifest, but no Arabic / Bengali strings exist and no layout has been mirrored.

### 2.10 Missing screens for the customer demo
- Onboarding (3)
- Permission priming (location + notification)
- Trusted contacts list + add/edit
- Profile edit
- Verify phone (OTP), verify email (OTP)
- Incident detail (user side)
- Incident detail (admin side, with map + responder list + actions)
- User detail (admin side)
- Notification center
- Settings (real)

---

## 3. Design System (commit to this first)

### 3.1 Tokens

```
// feature-core/ui/AmanahSpacing.kt
object AmanahSpacing {
    val xxs = 2.dp
    val xs  = 4.dp
    val sm  = 8.dp
    val md  = 16.dp
    val lg  = 24.dp
    val xl  = 32.dp
    val xxl = 48.dp
}

// feature-core/ui/AmanahElevation.kt
object AmanahElevation {
    val none = 0.dp
    val low  = 1.dp
    val md   = 2.dp
    val high = 4.dp
    val xhi  = 8.dp
}

// feature-core/ui/AmanahMotion.kt
object AmanahMotion {
    const val FAST = 150
    const val NORMAL = 300
    const val SLOW = 600
    val EASE_OUT = EaseOutCubic
}

// feature-core/ui/AmanahTouch.kt
object AmanahTouch {
    val MIN_TOUCH_TARGET = 48.dp
}
```

### 3.2 Reusable components (10 to build first)

| Composable | Purpose | Replaces (in current code) |
|---|---|---|
| `AmanahScaffold` | Wraps Scaffold + TopAppBar + SnackbarHost + bottom-nav slot. Subscribes to global `SnackbarBus`. | every `*View.kt` re-Scaffold |
| `AmanahTopBar(title, subtitle, actions, navigationIcon)` | Branded top bar (preserves Amanah typography + status-bar padding) | All TopAppBar usage |
| `AmanahPrimaryButton(text, loading, enabled, onClick)` | The single "primary CTA" button | All `Button { Text(...) }` blocks |
| `AmanahSecondaryButton(...)` | Outlined variant | All `OutlinedButton {}` |
| `AmanahDestructiveButton(...)` | Red error-coloured primary | "Cancel Emergency", "Sign Out", "Force Resolve" |
| `AmanahCard(elevation = md, padding = md)` | Standard card | Every `Card { Column(Modifier.padding(...)) {} }` |
| `AmanahLoadingState(message)` | Centered progress + optional message | `CircularProgressIndicator` boxes |
| `AmanahEmptyState(icon, title, body, actionText, onAction)` | Empty list / no data state | inline `Text("No alert history", ...)` |
| `AmanahErrorState(message, onRetry)` | Generic error with retry | `DashboardView.ErrorPanel` |
| `AmanahPullToRefresh(state, onRefresh, content)` | Standard pull-to-refresh | currently not implemented anywhere |

### 3.3 Lints
- `compose-rules` lint to enforce: top-level composables use stable params; `@Stable` annotations on view-models; no `LaunchedEffect(Unit)` for one-shot side effects without a key justification.
- Detekt rule banning `Modifier.padding(\d+\.dp)` outside of `AmanahSpacing.*`.

---

## 4. Screen-by-Screen Priority

Legend:
- **P0** = required for customer demo (day 7)
- **P1** = required for MVP (week 4)
- **P2** = required for production (month 3)

### Onboarding & Auth flow

| Screen | Priority | Effort (eng-h) | Notes |
|---|---|---|---|
| Splash (animated logo) | ✅ exists | — | Replace placeholder Arabic glyph with branded SVG. 1h |
| Onboarding 1 — "Welcome to Amanah" | P0 | 4 | Slide 1: trust your community |
| Onboarding 2 — "One tap to call for help" | P0 | 4 | Slide 2: emergency button concept |
| Onboarding 3 — "Privacy by design" | P0 | 4 | Slide 3: location obfuscation explained |
| Permission Priming (location) | P0 | 6 | Custom screen before system prompt |
| Permission Priming (notification) | P0 | 4 | Same pattern |
| Login | ✅ exists | wire 2 | Bind to AuthRepository |
| Password Reset request | ✅ exists | wire 2 | Bind to backend; show pending-approval state |
| Email verification (OTP) | P1 | 8 | New screen |
| Phone verification (OTP) | P1 | 8 | New screen |
| Biometric login enrol (optional) | P2 | 16 | androidx.biometric already in classpath |

### User dashboard

| Screen | Priority | Effort | Notes |
|---|---|---|---|
| Home tab (idle nearby grid + Emergency button) | ✅ exists | wire 8 | Replace stub with `UserRepository.getNearbyActiveUsers()` |
| Emergency button (long-press, pulse) | ✅ exists | — | Already polished |
| Active-emergency overlay (full screen map) | ✅ exists | wire 4 | Wire `wsPublish` lambda |
| Alerts (history) tab | ✅ exists empty | 6 | Real `getAlertHistory()`, sort, filter |
| Alert detail (user) | P0 | 12 | New screen — opened from history card AND the active overlay |
| Profile tab (read-only) | ✅ exists | wire 4 | Bind to `/users/me` |
| Edit profile | P1 | 12 | Form + form validation |
| Verify phone (from profile) | P1 | 8 | OTP entry sub-screen |
| Verify email (from profile) | P1 | 8 | OTP entry sub-screen |
| Trusted contacts list | P1 | 12 | Port from amanah18 |
| Trusted contact add / edit | P1 | 12 | Form |
| Settings tab — real | P1 | 16 | Notifications, location precision, language, about |
| Notification center | P1 | 16 | Backed by `/notifications` API |
| Logout confirmation dialog | P0 | 2 | Currently logs out without confirmation |

### Admin dashboard

| Screen | Priority | Effort | Notes |
|---|---|---|---|
| Users tab | ✅ exists | wire 6 | Replace stub with `AdminRepository.listUsers()` |
| User card (approve / suspend / edit actions) | ✅ exists | wire 4 | Wire actions to `POST /admin/...` |
| User detail (full) | P0 | 16 | New screen — devices, audit log section, role assignment, suspend reason |
| Edit user | P0 | 12 | Form-based |
| Approvals queue (separate from Users tab) | P1 | 12 | Currently surfaced as a badge only; needs a dedicated screen |
| Alerts tab (alert log) | ✅ exists | wire 4 | Bind to backend; subscribe to WS |
| Alert detail (admin) | P0 | 16 | Map + responder list + actions (force-resolve, escalate, contact victim) |
| Stats tab | ✅ exists | 4 | Bind to real counts; add small charts (e.g. last-7-days sparkline) |
| Audit log viewer | P1 | 16 | Filterable, paginated |
| Organisations list | P1 | 12 | Port from React admin-panel |
| Organisation detail | P2 | 12 | |
| Regions list | P1 | 12 | |
| Regions on map | P2 | 16 | PostGIS polygon viewer |
| Roles list | P1 | 8 | |
| Role permissions editor | P2 | 16 | |
| Settings (admin) | P1 | 12 | |

### Cross-cutting

| Screen / pattern | Priority | Effort | Notes |
|---|---|---|---|
| Global snackbar bus | P0 | 4 | Replace `/* wire to global toast */` TODOs |
| Connectivity banner (offline) | P0 | 6 | Top inset banner when WS is disconnected |
| In-app version + crash diagnostic in Settings | P1 | 4 | BuildConfig.VERSION_NAME + crash count |
| Force-update screen | P2 | 8 | Backend returns min-app-version |
| Maintenance screen | P2 | 4 | Backend returns 503 with maintenance flag |

---

## 5. Customer Demo Storyboard

**Persona A — community member (USER role):**

1. App launches → animated splash (2.0s).
2. *First time:* Onboarding 1 → 2 → 3.
3. Permission priming: location + notification.
4. Login screen — enter `member@demo.com` / `Demo1234!` → press *Sign In*.
5. Land on **User Dashboard / Home tab**. See 3 fake nearby members (real backend stub: "demo-org" + seeded users).
6. Tap *Settings* tab → toggle dark mode → return to Home.
7. **Long-press the red Emergency button** (haptic). Banner appears: *"Emergency alert ACTIVE — Responders notified"*.
8. Screen transitions to full-screen **Emergency overlay**:
   - Red header bar "EMERGENCY ALERT — Alert #ABC123".
   - Map centred on the victim, pulse zoom.
   - 3 staged fake responder markers slide in over ~10s, ETA card animates "Calculating…" → "8 min · 700m away".
9. Wait 30s while the demo dispatcher reduces ETA to "3 min".
10. Tap *Dismiss Alert* → confirmation dialog → back to Home.

**Persona B — administrator (ADMIN role) on a second device:**

1. Login as `admin@demo.com`.
2. Land on **Admin Dashboard / Users tab**. See the pending-approval badge.
3. Tap a pending user → **User Detail** → press *Approve*. Toast: "User approved."
4. Switch to *Alerts* tab. The alert from Persona A is visible at the top with red border, status `ACTIVE`.
5. Tap the alert → **Alert Detail (admin)** with map + responder list + *Force Resolve* action.
6. Press *Force Resolve* → reason dialog → confirm.
7. Persona A's device receives a status push → emergency overlay closes.
8. Switch to *Stats* tab → see the resolved-alert count increment.

**Stop conditions for demo:**
- Backend down → demo dispatcher won't fire → red banner on connectivity layer.
- Background → emergency state must persist (background service / FCM resurfacing).

---

## 6. Asset & Brand Checklist

| Asset | Status | Action |
|---|---|---|
| App icon (mipmap-anydpi-v26 + adaptive) | ❌ default Android icons | Commission a brand icon (foreground vector + monochrome) |
| Splash logo (vector) | ❌ placeholder text "أ" | Commission vector SVG → ImageVector |
| Light wordmark / dark wordmark | ❌ | Need both for top bars |
| Onboarding illustrations × 3 | ❌ | Commission |
| Empty-state illustrations × 4 | ❌ | "no alerts", "no nearby", "no trusted contacts", "no notifications" |
| Permission-priming illustrations × 2 | ❌ | Location + notification |
| Color palette PDF | ⚠️ defined in code only | Export tokens.json + Figma library |
| Typography ramp | ⚠️ Compose Typography only | Export Material 3 type roles |
| Iconography set | ⚠️ Material icons | Define outline/filled rule + custom safety/SOS icons |
| Tone-of-voice guide | ❌ | Short — 1 page (active voice, urgency in red banners, calm green confirmations) |
| Sound design | ❌ | Optional but recommended: alert chime, responder-en-route chime |

---

## 7. Accessibility Plan

| Item | Status | Action |
|---|---|---|
| TalkBack walkthrough | ❌ | Test every flow with TalkBack |
| Content descriptions on icons | ⚠️ partial | Audit & fix |
| 48dp min touch targets | ⚠️ unverified | Audit & fix |
| Font scale 130% / 200% | ❌ untested | Test |
| Colour contrast (WCAG AA) | ⚠️ untested | Run a contrast check on every text-on-background pair |
| RTL mirror (AR / UR) | ❌ | Test with `compileResources("ar")` |
| Haptic alternatives | ❌ | EmergencyButton long-press currently relies on haptic feedback; add visual progress ring |
| High-contrast theme | ❌ | Add `AmanahHighContrastTheme` variant |
| Reduce-motion support | ❌ | Honour `Settings.Global.TRANSITION_ANIMATION_SCALE` |

---

## 8. UI Risks / Open Questions

| Question | Owner | Decision needed by |
|---|---|---|
| Single role per user, or can someone be both USER and ADMIN? | Product | Day 1 |
| Are responders a *separate role* (RESPONDER), or just USERs with availability toggle? amanah18 modelled both; new code only has ADMIN/USER. | Product | Day 1 |
| Is silent SOS a feature (no audible alert)? amanah18 has `silent_mode` on Incident model; new code doesn't. | Product | Week 2 |
| What languages launch with? EN only, or EN+AR+BN at launch? | Product | Week 2 |
| Does the app support tablets / foldables on day 1? | Product | Week 4 |
| What does the brand actually look like (logo, illustrations, tone)? | Design | Day 1 |
| Will the demo use real GPS, or seeded coordinates? | Eng | Day 4 |
| Multi-device session: log out everywhere vs. per-device? amanah18 supports `/auth/logout/all`. | Product | Week 2 |
| MFA — required for ADMIN at MVP? amanah18 has TOTP. | Security | Week 2 |

---

## 9. UI Acceptance Criteria for "demo-ready"

A screen counts as demo-ready when:
1. Uses `AmanahScaffold` + design tokens (no raw `dp` literals outside `AmanahSpacing`).
2. Renders a real loading state (`AmanahLoadingState`), real empty state (`AmanahEmptyState`), and real error state with retry (`AmanahErrorState`).
3. Has `contentDescription` on every icon.
4. Has at least one happy-path Compose UI test.
5. Has been TalkBack-walked once.
6. Is reachable from `RootNode` (no dead-end screens).
7. Does NOT show hard-coded `Aisha`/`Omar` names in release builds.
8. Surfaces backend errors via `GlobalSnackbarBus`.

For full *production* readiness add: RTL mirror, font-scale 200%, contrast pass, haptic alternative, dark + light parity tested.

---

## 10. Effort & Sequencing Table

```
PRIORITY  ITEM                                  EFFORT
─────────────────────────────────────────────────────
P0        Delete dead Islamic dashboard         0.25d
P0        Design tokens + 10 widgets            1.5d
P0        Replace placeholder splash logo       0.25d
P0        Onboarding 3 screens                  1.0d
P0        Permission priming (loc + notif)      0.5d
P0        Wire LoginView to backend             0.5d
P0        Wire UserDashboard idle / emergency   1.5d
P0        Wire AdminDashboard                   1.0d
P0        Alert detail (user)                   1.0d
P0        Alert detail (admin)                  1.5d
P0        Global snackbar bus + connectivity    1.0d
P0        Demo seed data + fake responder       0.5d
─────────────────────────────────────────────────────
                            TOTAL P0:         ~10.5d ⇒ DEMO

P1        Trusted contacts                      2.0d
P1        Edit profile + verify phone/email     2.5d
P1        Settings (real)                       1.5d
P1        Notification center                   1.5d
P1        Admin approvals / user detail / audit 4.0d
P1        Admin orgs / regions / roles          3.0d
─────────────────────────────────────────────────────
                            TOTAL P1:         ~14.5d ⇒ MVP

P2        Tablet / fold layouts                 5d
P2        Wear OS companion                     8d
P2        Force-update / maintenance screen     1d
P2        Multi-language launch (AR + BN)       3d
P2        Accessibility full pass               2d
─────────────────────────────────────────────────────
                            TOTAL P2:         ~19d
```

— end of UI / UX MVP plan
