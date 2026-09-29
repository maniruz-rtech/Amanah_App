# Realtime Hardening Plan

**Scope:** retire Scarlet, harden the realtime channel that carries emergency alerts and responder positions, and put the system on production-survivable footing.

**Mission constraint:** this is not a chat app. Lost or duplicated alerts are safety incidents. Every choice below leans toward *deterministic, observable, debuggable* over *clever*.

---

## 1. What changed at a glance

| Concern | Before | After |
|---|---|---|
| WebSocket library | Scarlet 0.2.0 (abandoned since ~2020) | `OkHttpRealtimeGateway` — OkHttp `WebSocketListener` behind a thin Reaktive wrapper |
| Auth on socket | `wss://host/ws?token=<jwt>` (token in URL) | `Authorization: Bearer <jwt>` HTTP header at upgrade |
| TLS pinning | none | OkHttp `CertificatePinner` — primary + backup SPKI hashes on both HTTPS and WSS clients |
| Token storage | `androidx.security:security-crypto:1.1.0-alpha06` (deprecated) | Tink AEAD + Jetpack DataStore with Android-Keystore-wrapped master key |
| Reconnect | implicit (Scarlet internals) | deterministic FSM — truncated-exponential backoff with full jitter |
| Heartbeat | none explicit | `HeartbeatScheduler` — 25 s ping + 10 s pong watchdog |
| Duplicate-event protection | none | 512-entry LRU `EventDedup` by server `event_id` |
| Acknowledgements | none | `AckRegistry` exposes a `SendOutcome` observable per envelope |
| Offline queue | none | `OutboundQueue` with per-envelope TTL |
| R8 / release safety | no rules | `app/proguard-rules.pro` with annotated rationale per stanza |
| Lifecycle | hidden inside Scarlet | explicit `AppForegroundObserver` ↔ `RealtimeGateway` bridge |
| Single integration seam | per-channel interfaces | one `RealtimeGateway` consuming a `RealtimeEnvelope` |

---

## 2. Architecture target

```
Compose UI
    │
MVICore Feature
    │
Interactor / Repository
    │
RealtimeGateway (interface)
    │
OkHttpRealtimeGateway
    ├─ ReconnectStrategy        (pure backoff function)
    ├─ HeartbeatScheduler       (ping + dead-server detection)
    ├─ OutboundQueue            (TTL-aware FIFO)
    ├─ AckRegistry              (per-eventId SendOutcome)
    ├─ EventDedup               (LRU of server-assigned event_ids)
    └─ AppForegroundObserver    (external lifecycle hook)
        │
OkHttp WebSocketListener
        │
Authorization: Bearer <JWT>            ← header, never query string
        │
TLS + CertificatePinner (primary + backup)
        │
FastAPI /ws  (websocket_v2.py)         ← header-based authn
```

Key properties of the design:

- **Explicit lifecycle.** The composition root calls `connect()` after sign-in and `disconnect()` on logout. No invisible auto-connect; no hidden background reconnect after logout.
- **One envelope.** Every inbound/outbound frame uses the same `{ v, type, event_id, ts, payload }` shape. Ordering, deduplication and ACK are envelope-layer concerns — payload semantics are added by parsers.
- **Deterministic reconnect.** `ReconnectStrategy.delayFor(attempt)` is a pure function of attempt count. Testable, no hidden timers.
- **Mission-critical primitives are first-class objects.** Each (heartbeat, queue, ack, dedup) lives in its own file with its own tests later.

---

## 3. Migration sequence

We deploy in seven steps, each independently reversible.

| # | Change | Surface area | Risk | Rollback |
|---|---|---|---|---|
| 1 | Add `OkHttpRealtimeGateway` alongside Scarlet | client | none — feature flag selects | flip flag |
| 2 | Add Tink store alongside ESP — Tink reads old data and re-encrypts | client | none — old keystore preserved | flip flag, ESP still has data |
| 3 | Backend: add `websocket_v2.py` mounting `/ws` with header auth; keep `/ws-legacy` accepting `?token=` for the Flutter app | backend | none — additive | unmount router |
| 4 | Client cuts over to `OkHttpRealtimeGateway` + `/ws` header auth | client | medium — release-gated | rollback to flagged-off build |
| 5 | Client cuts over to Tink store; ESP file deleted after read | client | low — token loss = forced re-login | re-install |
| 6 | Backend removes legacy `?token=` path | backend | low — only Flutter clients affected; Flutter is being deprecated | re-mount router |
| 7 | Client repo: delete Scarlet + `androidx.security` dependencies; clean BUILD files | client | none — purely cosmetic | revert commit |

Each step is a separate PR. Steps 1, 2, 3 can land in parallel. Step 4 must wait for step 3 to be in production for ≥ 1 day.

---

## 4. Acceptance criteria

A step counts as done when:

- All unit tests for the new component pass.
- The debug drawer shows the relevant FSM transitioning (connecting → online → reconnecting → online) under simulated network flap (`adb shell svc wifi disable && adb shell svc wifi enable`).
- Pinning verified: with a swapped cert (use mitmproxy with a custom CA), the gateway terminates with `TLS_FAILED`; with the correct cert it accepts.
- Logging audit: `grep -i 'token\|jwt\|bearer'` over a 5-minute logcat capture shows zero hits in both debug and release builds.

---

## 5. Deferred / next iteration

These are deliberate omissions — picked up after the current hardening lands.

| Item | Why deferred | Tracking |
|---|---|---|
| Persist `OutboundQueue` to DataStore-Proto (survives process death) | Demo doesn't need it; PRD requires within MVP | follow-up PR |
| Header-only auth (drop the `Sec-WebSocket-Protocol` fallback) once browser admin client is replaced | One transition at a time | post-Flutter-decom |
| Server-side rate limit on envelope `send` | Wait for telemetry on real send volume | post-launch |
| Device binding (`X-Amanah-Device-Id` claim cross-checked server-side) | Needs server work + a device-ID provisioning flow | next sprint |
| FIDO2 / hardware-bound refresh tokens | Roadmap item — Android Credential Manager | medium-term |

---

## 6. Companion docs

- [WEBSOCKET_SECURITY_ARCHITECTURE.md](WEBSOCKET_SECURITY_ARCHITECTURE.md) — header auth, TLS, threat model
- [TOKEN_STORAGE_MIGRATION.md](TOKEN_STORAGE_MIGRATION.md) — Tink + DataStore, ESP migration
- [CERTIFICATE_PINNING_GUIDE.md](CERTIFICATE_PINNING_GUIDE.md) — SPKI extraction + rotation runbook
- [R8_RELEASE_HARDENING.md](R8_RELEASE_HARDENING.md) — release validation checklist
- [REALTIME_RELIABILITY_STRATEGY.md](REALTIME_RELIABILITY_STRATEGY.md) — heartbeat / ack / dedup / queue
