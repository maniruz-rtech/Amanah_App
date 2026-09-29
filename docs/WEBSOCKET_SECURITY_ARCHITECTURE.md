# WebSocket Security Architecture

## Threat model summary

The realtime channel carries:
- Outbound: emergency alerts (lat/lng + victim identity), responder location during ACTIVE incidents.
- Inbound: alert broadcasts, responder positions, admin notifications.

Both directions are PII-sensitive and safety-critical. We design against an adversary who can:

1. **Observe the network** (corporate proxy, ISP, public Wi-Fi).
2. **Inject TLS termination** (corporate root CA installed on user device, captive portal).
3. **Compromise a single backend instance** (without keys).
4. **Steal an access token** (logs, analytics, leaked URL).
5. **Replay or reorder envelopes** (man-in-the-middle, broken proxy).

We do **not** defend against:
- A rooted device with the user's biometric. Anything that can read the Android Keystore can recover tokens; this is accepted (a user with a rooted device handling their own SOS is already in a different threat class).
- Side-channel timing attacks on the JWT — out of scope.

---

## 1. Token transport

**Rule:** tokens travel only inside `Authorization: Bearer <jwt>` headers. Never in:

| Channel | Reason |
|---|---|
| URL query string | Logged by reverse proxies, LB access logs, browser history (web admin), analytics SDKs. |
| Path segment | Same as query string. |
| Cookie | Not used; would create CSRF surface and is not needed for native clients. |
| Local broadcast / Intent extras | An exported component on the device could intercept. |
| Crash reports | Sentry / Crashlytics dumps headers by default — see redaction below. |
| Logs | `HttpLoggingInterceptor` is configured with `redactHeader("Authorization")`. |

Implementation:
- HTTPS: `AuthInterceptor` adds the header per request.
- WSS: `OkHttpRealtimeGateway.doOpen()` adds the header on the upgrade request (`Request.Builder().addHeader("Authorization", "Bearer …")`).

---

## 2. WebSocket handshake — client → server

```
GET /ws HTTP/1.1
Host: api.amanah.example
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <random>
Sec-WebSocket-Version: 13
Authorization: Bearer <jwt>
X-Amanah-Client: android
```

`X-Amanah-Client` lets the server route by client type and enforce per-client rate-limits without parsing the JWT.

Server response (success):

```
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <hash>
```

Server response (token rejected):

```
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

`OkHttpRealtimeGateway` catches a 401 in `onFailure` (`response.code == 401`) and terminates with `AUTH_REJECTED`, surfacing a "sign in again" affordance to the user. It does **not** reconnect.

### Browser fallback

Browser `WebSocket(url, protocols)` cannot set arbitrary headers. The backend therefore also accepts the token via the `Sec-WebSocket-Protocol` sub-protocol negotiation:

```
Sec-WebSocket-Protocol: amanah, <jwt>
```

Used only by the web admin in the transition period. The Android client never uses this path.

---

## 3. Post-handshake authentication envelope

The TCP handshake authenticated the *transport*. We still expect the server to send a typed `auth.accepted` envelope before the gateway declares `Online`. This:

- Lets the backend perform additional checks asynchronously (device binding, JWT revocation list lookup) without blocking the upgrade response.
- Gives the client a deterministic moment to enter the Online state.
- Makes the server able to reject a connection *after* it accepted the TCP upgrade (e.g. a stolen-token rotation detected mid-upgrade).

```json
{ "v":1, "type":"auth.accepted", "event_id":"…", "ts":1715000000000, "payload":{ "user_id":"usr_…" } }
```

If the server emits `auth.rejected` instead, the gateway terminates with `AUTH_REJECTED`.

---

## 4. Channel integrity

| Property | Mechanism |
|---|---|
| Confidentiality | TLS 1.2+ (system trust store) + certificate pinning (see [CERTIFICATE_PINNING_GUIDE.md](CERTIFICATE_PINNING_GUIDE.md)). |
| Integrity | TLS record MAC. |
| Authentication | JWT signature checked by the server. |
| Replay protection | Envelope `event_id` is a UUIDv4; server deduplicates and the client's `EventDedup` rejects duplicates within an LRU window. Outbound envelopes carry an optional `ttl_ms` so a queued-but-undelivered emergency alert does not fire days later. |
| Reordering | Envelopes carry server `ts`; the client processes in arrival order but uses `ts` for any UI ordering. The server is the order authority. |

---

## 5. WebSocket hijacking / session fixation

Threats:

- **Token captured from URL logs (legacy `?token=` path)** — eliminated by switching to header auth.
- **Forged Origin header** — `WebSocket` doesn't strictly honor `Origin` for native clients; instead, the server enforces JWT validation as the source of truth.
- **TCP-level hijack on a non-TLS network** — prevented by enforcing `wss://` (the client refuses `ws://` outside debug builds) plus pinning.

---

## 6. Unauthorized emergency broadcast

The client can send `emergency.alert` envelopes. The server **must not trust** them:

- The user_id in the envelope is overridden by the JWT-derived user_id.
- Geographic broadcast list (k-ring) is computed server-side from the verified user's last-known H3 cell, not from envelope claims.
- Rate-limit: at most 1 active emergency per user; further triggers are rejected.

(These are server-side controls — see backend issue tracker for verification status.)

---

## 7. Fake responder broadcast

The server attaches the JWT-derived `responder_id` to every `responder.location` envelope before fanning out. A compromised client cannot impersonate another responder by spoofing the `responder_id` field.

---

## 8. Stale session detection

- JWT `exp` is checked client-side before each request (interceptor pre-flight, deferred — see TECHNICAL_DEBT_REPORT C3).
- 401 on REST → automatic refresh once → on second 401 → `onSessionExpired()` → gateway disconnects + user reroute to login.
- The gateway hard-fails on TLS pin mismatch (`SSLPeerUnverifiedException`). No silent fallback.

---

## 9. Audit trail

Every state transition of `RealtimeConnectionState` is logged via the `logger` callback passed into `OkHttpRealtimeGateway`. In debug builds this is logged to `Log.d("RealtimeGateway", …)`. In production, hook this into the same telemetry sink as crash reports (Sentry breadcrumbs) — never log token values; redact at the interceptor level.

---

## 10. Open questions / non-goals

- **Cookie-based fallback** — not implemented. Native clients have no need.
- **mTLS** — not used; pinning + JWT is sufficient at our threat level and avoids per-device cert provisioning.
- **Token binding** (RFC 8471) — out of scope; not supported by FastAPI without significant work.
