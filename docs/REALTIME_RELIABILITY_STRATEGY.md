# Realtime Reliability Strategy

This is an emergency-response system. The realtime channel exists so a user
who triggered an SOS gets help. Reliability is mission-critical; the
strategy below is built for *predictable behaviour under stress*, not
nine-decimal-places-of-uptime claims.

## Reliability primitives

| Component | File | Role |
|---|---|---|
| `RealtimeGateway` | `RealtimeGateway.kt` | Single integration seam; explicit `connect/disconnect/send`. |
| `OkHttpRealtimeGateway` | `OkHttpRealtimeGateway.kt` | Concrete OkHttp-backed impl with the FSM below. |
| `RealtimeConnectionState` | `RealtimeConnectionState.kt` | Strict sealed-class FSM (Idle / Connecting / Authenticating / Online / Reconnecting / Terminated). |
| `RealtimeEnvelope` | `RealtimeEnvelope.kt` | Single wire shape. Ordering + dedup are envelope-layer. |
| `RealtimeEvent` | `RealtimeEnvelope.kt` | Sealed inbound event taxonomy. Compile-time exhaustive. |
| `ReconnectStrategy` | `ReconnectStrategy.kt` | Pure truncated-exponential backoff with full jitter. |
| `HeartbeatScheduler` | `HeartbeatScheduler.kt` | Ping every 25 s; pong watchdog 10 s. |
| `OutboundQueue` | `OutboundQueue.kt` | FIFO queue with per-envelope TTL. |
| `AckRegistry` | `AckRegistry.kt` | Per-eventId `SendOutcome` observables. |
| `EventDedup` | `EventDedup.kt` | LRU 512 — duplicate inbound `event_id`s dropped. |
| `AppForegroundObserver` | `AppForegroundObserver.kt` | Bridges `ProcessLifecycleOwner` into the gateway. |

## Connection FSM

```
              connect()
            ┌────────────┐
            ▼            │
   ┌──────────┐   401   ┌─────────────┐ socket fail
   │CONNECTING│────────►│ TERMINATED  │◄────────────┐
   └─────┬────┘ TLS fail│(AUTH_REJ /  │             │
         │ open         │ TLS_FAILED) │             │
         ▼              └─────────────┘             │
   ┌────────────────┐                              │ exhausted
   │AUTHENTICATING  │ auth.rejected ▲              │ retries
   └─────┬──────────┘ ─────────────┘              │
         │ auth.accepted                          │
         ▼                                        │
   ┌──────────┐  socket fail / missed pong ┌────────────┐
   │  ONLINE  │ ──────────────────────────►│RECONNECTING│
   └─────┬────┘                            │ (n, delay) │
         │ disconnect()                    └─────┬──────┘
         ▼                                       │ timer
   ┌──────┐                                      │
   │ IDLE │◄─────────────────────────────────────┤
   └──────┘   disconnect() from any state         │
                                       (back to CONNECTING)
```

State transitions are emitted on a `BehaviorSubject<RealtimeConnectionState>`
so any subscriber (UI, debug drawer, telemetry) sees both the *current* and
*subsequent* values without race conditions.

## Reconnect strategy

```
delay(attempt) = random(0, schedule[min(attempt, last)])

schedule = [1s, 2s, 5s, 10s, 30s, 60s]
giveUp   = attempt >= 30 || totalElapsed >= 30 min
```

Why this curve, not pure exponential:

- For an emergency app, fast early reconnects matter most. The first 10 s
  cover ~90 % of network blips (lift / metro / lap-shut).
- After 30 s we throttle hard to protect the server from a stampede.
- Full jitter (every delay is `random(0, ceiling)`) defeats synchronised
  client retries after a backend deploy.

After 30 minutes or 30 attempts the gateway transitions to
`Terminated(SERVER_FATAL)`. The app surfaces an explicit "cannot reach
Amanah" banner — the user can retry manually with `connect()`.

## Heartbeat

| Setting | Value | Reason |
|---|---|---|
| Ping period | 25 s | Below Cloudflare's 100 s idle limit and AWS ALB's default 60 s. |
| Pong timeout | 10 s | Twice the typical 3G RTT (~3 s); generous enough to avoid false positives, tight enough to catch hung sockets quickly. |

The watchdog fires `onDead` when `now - lastPongMs > pingPeriod + pongTimeout`. The gateway closes the socket and transitions to `Reconnecting`.

Heartbeats use the same `RealtimeEnvelope` shape (`type = "ping"` / `"pong"`) so the wire format is uniform.

## Acknowledgement protocol

```
Client → Server                                Server → Client
─────────────                                  ─────────────
{ type:"emergency.alert",                      { type:"ack",
  event_id:"e1",                                 event_id:"e1",
  ttl_ms:60000,                                  payload:{ "event_id":"e1" } }
  payload:{ … } }
```

- Every non-`ping` envelope sent by the client gets an `ack`.
- `AckRegistry` returns a `SendOutcome` observable per `event_id`.
- On ACK → `SendOutcome.Acknowledged(eventId)`.
- On TTL expiry without ACK → `SendOutcome.Failed(eventId, "ttl expired")`.
- On gateway disconnect → all pending ACKs fail with `"disconnected"`.

This gives the UI a clear contract: an emergency alert either reports
*delivered* or *failed* — never silent.

## Deduplication

The server emits an `event_id` for every fan-out delivery. Under reconnect
the server **re-delivers** events the client may not have processed yet
(at-least-once semantics).

`EventDedup` is an LRU of size 512:

- New `event_id` → forwarded to the `incoming` stream.
- Seen `event_id` → silently dropped.
- LRU eviction means a duplicate that arrives > 512 events later would be
  re-processed. We size for the worst-case reconnect storm (≤ 30 min × 1 Hz
  responder updates ≈ 1800 events — too high; we'd resize if it bit us).

**ACK and PONG are not dedup-checked**. They're transport-layer signals, not
business events.

## Offline queue

`OutboundQueue` stores envelopes the gateway couldn't transmit (socket
offline). When the gateway transitions Online → it drains:

1. Drop any envelope past its `ttl_ms` deadline; emit `SendOutcome.Failed`.
2. Send the rest in FIFO order.

Today the queue is in-memory. **Process death wipes it.** This is the
single most-important reliability gap to close before production:
back the queue with DataStore-Proto so an SOS triggered in airplane mode
flushes on next launch. The interface is shaped to take that swap.

## Lifecycle policy

The gateway does **not** auto-close on background. Emergency apps must stay
connected — a user who locked their phone after triggering an alert still
needs responder updates to flow.

`AppForegroundObserver` calls `onForeground` / `onBackground` for telemetry
and to kick a reconnect if we were in `Idle`, but does not tear the socket
down.

If a future PRD says "tear down after 5 min in background to save battery"
that's a single-line change in `onBackground()`.

## Stale connection detection

Three layers:

1. **TCP keepalive** (OkHttp default — kernel-level).
2. **Application heartbeat** — `HeartbeatScheduler`.
3. **Server-emitted closure** — explicit close-frame on logout, kick, or
   server restart. Gateway treats as a normal `onDropped` → reconnect.

Note we explicitly disable OkHttp's `pingInterval` — using OkHttp's pings
would conflict with our application-level envelope pings and the server
would see two different framing.

## Event ordering

The server is the authority. Each envelope carries server `ts`. The client
processes envelopes in receive order but uses `ts` for any UI ordering
operation (e.g. sorting alerts by triggered-time). We **never** trust the
client clock for ordering, because Android's `System.currentTimeMillis()` can
go backwards (NTP, user-set time).

## Observability

- Every FSM transition is logged via the gateway's `logger` callback. In
  debug builds → `Log.d("RealtimeGateway", …)`. In release → wire to
  Sentry breadcrumbs (deferred).
- The debug drawer shows current state, attempt count, queue size, pending
  ACKs, dedup cache size. Tap to copy a connection-state report for bug
  reports.

## Failure-mode catalogue

| Failure | Detection | Response |
|---|---|---|
| Network drop | OkHttp `onFailure(IOException)` | `Reconnecting(attempt, delay)`; queue retains envelopes; ACKs delayed |
| 401 at handshake | OkHttp `onFailure` with `response.code == 401` | `Terminated(AUTH_REJECTED)`; pending ACKs fail; user routed to login |
| TLS pin mismatch | `SSLPeerUnverifiedException` | `Terminated(TLS_FAILED)`; **no retry** |
| Server hang (no pong) | `HeartbeatScheduler.checkPong` | Force-close socket; `Reconnecting`; queue retains envelopes |
| Server emits malformed JSON | `decode()` returns null | Log warn; skip envelope |
| Server emits unknown `type` | `RealtimeEventParser.parse` returns `RealtimeEvent.Unknown` | Surface for diagnostics; don't crash |
| Server emits duplicate event | `EventDedup.firstSeen` → false | Silently drop |
| Outbound envelope TTL expires | `OutboundQueue.drainEligible` | `SendOutcome.Failed(eventId, "ttl expired")` |
| Client kills the process during active emergency | (current limitation) | Outbound queue lost. Mitigation in next iteration: DataStore-backed queue. |
| Process forced into Doze | Foreground service holds wake-lock during active emergency | (deferred — see TECHNICAL_DEBT_REPORT B10) |

## SLOs (targets, not promises)

| Metric | Target |
|---|---|
| Time-to-online from cold connect (best 4G) | < 2 s p95 |
| Time-to-reconnect after server restart | < 5 s p95 (within first backoff slot) |
| Emergency-alert delivery latency (sent → ACK) | < 1 s p95 |
| Inbound emergency-alert delivery (server fanout → UI update) | < 2 s p95 |
| False-positive pong watchdog (incorrect socket teardown) | < 0.1 % per 24 h online time |
| Duplicate alert UI fire | 0 (any duplicate is a P1 bug) |

These are *aspirations* — they become commitments once we have telemetry in
place.

## Testing strategy

Unit-testable in isolation:

- `ReconnectStrategy.delayFor` — pure function; trivially testable with a seeded `Random`.
- `EventDedup.firstSeen` — pure state-machine; deterministic.
- `OutboundQueue` — TTL-eviction edge cases.
- `AckRegistry` — observable subscription / completion semantics.
- `RealtimeEventParser.parse` — every event type, missing fields, type mismatches.
- `HeartbeatScheduler` — fake `ScheduledExecutorService` + manual time.

End-to-end (requires a test server):

- Network-flap test: `iptables -A OUTPUT -p tcp --dport 8000 -j DROP` for 2/5/30 s; verify reconnect behaviour matches `ReconnectStrategy.SCHEDULE`.
- Pong-loss test: server-side stub stops responding to pings; verify watchdog fires within ping + pong window.
- TTL test: trigger SOS while disconnected; wait > 60 s; reconnect; verify `SendOutcome.Failed("ttl expired")`.
- Dedup test: server replays the same `event_id` twice; verify UI sees one event.

(None of these are implemented yet — see TECHNICAL_DEBT_REPORT E1.)
