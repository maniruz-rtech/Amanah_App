# Offline Durability Plan

For an emergency-response app, a triggered SOS that's lost when the user's
phone runs out of battery, loses connectivity mid-trigger, or has the app
process killed by the OS is a **safety incident**, not just a UX paper-cut.

This document covers the two persistence axes:

1. **Trigger durability** — what happens between long-press and the
   committed DB row.
2. **Realtime durability** — what happens to outbound envelopes (presence,
   responder location updates) when the WebSocket is offline.

---

## 1. Trigger durability

The trigger path is **REST**, not WebSocket. That's the first line of
defense:

- `EmergencyRepository.createSos` retries up to 4 attempts with full-jitter
  backoff (500 ms → 1 s → 2 s → 4 s) on NetworkDown and 5xx.
- OkHttp's `retryOnConnectionFailure = true` handles transient socket
  failures inside each attempt.
- Auth failures (401/403) fast-fail to a "please sign in" surface — no
  silent retry that would lose the user's context.

If all 4 retries exhaust, the engine emits `EmergencyWish.AlertError(message)`
and the UI shows a hard error. The user can long-press again — the second
attempt creates a fresh `event_id` and uses the same retry budget. There
is no silent loss.

### What we do NOT do

We do not queue SOS triggers durably for later retry. Reasoning:

- An SOS that arrives at the backend 4 hours later is no longer relevant.
- The user typed (long-pressed) and saw a UI flip; surfacing a hard error
  is correct — they need to know to retry or seek help by other means.
- Durable queueing risks resurrecting old triggers after the user has
  already moved on (with help arrived, or in a different location).

### Process death

If the app process is killed between long-press and HTTP response, the
SOS is **not** persisted on the next launch. This is a deliberate choice
for the reasons above. The user must explicitly retry.

A separate roadmap item ("background SOS via foreground service") will
hold the process alive across the trigger window using a foreground
notification — out of scope for this MVP.

---

## 2. Realtime durability — DurableOutboundQueue

For non-trigger envelopes (presence pings, responder location updates), we
DO queue durably. File: [DurableOutboundQueue.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/realtime/DurableOutboundQueue.kt).

### Contract

```kotlin
interface OutboundQueue {
    fun enqueue(envelope: RealtimeEnvelope)
    fun drainEligible(nowMs: Long = …): Drain   // partition (live, expired)
    fun isEmpty(): Boolean
    fun size(): Int
    fun clear()
}
```

Two implementations:

| Impl | Backing store | Process-death survival | Used in |
|---|---|---|---|
| `InMemoryOutboundQueue` | `ConcurrentLinkedDeque` | ❌ lost | Tests, previews |
| `DurableOutboundQueue` | DataStore Preferences (JSON list of entries) | ✅ survives | Production graph |

### Storage format

A single JSON-encoded list of `PersistedEntry` records under the key
`outbound_queue` in DataStore preferences file `amanah_outbound_queue`:

```json
[
  {
    "envelope": {
      "v": 1,
      "type": "responder.location",
      "event_id": "...",
      "ts": 1715000000000,
      "payload": { "lat": ..., "lng": ..., "eta_seconds": 180 },
      "ttl_ms": 30000
    },
    "enqueued_at_ms": 1715000000123
  },
  ...
]
```

Why DataStore Preferences (and not Proto-DataStore or Room):

- Queue size is small — bounded by gateway flush cadence (rarely > 5
  items in flight).
- DataStore Preferences guarantees atomic writes — no half-snapshot
  visible across process restart.
- No codegen step needed (Proto-DataStore would require .proto + plugin).
- Future swap to Proto-DataStore is non-breaking — the `OutboundQueue`
  interface is what the gateway depends on.

### Threading

Writes happen on `Dispatchers.IO` via a `SupervisorJob` scope. Reads from
`drainEligible` are synchronous via an in-memory mirror; the mirror is
hydrated lazily and synchronously on first access (boot-only cost ≈ a
few ms on a Pixel 7).

```kotlin
init {
    runCatching {
        runBlocking { hydrate() }
        initialised = true
    }
}
```

### TTL eviction

Every envelope carries an optional `ttl_ms`. `drainEligible(now)`
partitions the queue into:

- **live** — envelopes within their TTL, returned for sending.
- **expired** — `event_id`s that exceeded their TTL; the caller (gateway)
  fires `SendOutcome.Failed("ttl expired")` for each so the call-site's
  observable completes.

TTL values currently in use:

| Envelope type | TTL | Reason |
|---|---|---|
| `responder.location` | 30 s | Stale position data is misleading |
| `presence` | 60 s | Presence pings are heartbeats, not durable signals |
| `emergency.alert` | (n/a — REST only) | Trigger doesn't go through the queue |

### Failure modes handled

| Scenario | Outcome |
|---|---|
| App backgrounded for 2 minutes during reconnect | Hydration on resume; queue intact; envelopes flushed on next Online |
| Process killed by OS (low memory, force-stop) | Re-hydrated from DataStore on next launch |
| Device reboot | Same — DataStore persists across reboot |
| User logs out | `clear()` called; snapshot wipes DataStore |
| App data wiped (settings) | Queue is gone — same as a fresh install |
| Disk full during snapshot | DataStore write retries; in-memory mirror remains authoritative |

### NOT handled (acknowledged)

| Scenario | Mitigation |
|---|---|
| Process killed *between* hydration and first drain | Currently a 1-2 second window with no protection. Future: lock the snapshot until first successful flush of next session. |
| Queue grows unbounded if server is permanently down | We rely on TTL eviction. Future: cap queue length and drop oldest with `Failed("queue overflow")`. |

---

## 3. Token + session durability

Tokens are persisted via Tink AEAD + DataStore in `TinkTokenStore`. See
[TOKEN_STORAGE_MIGRATION.md](TOKEN_STORAGE_MIGRATION.md) for the threat
model.

Session rehydration on cold start (added this session):

```
RootNode.onAttach
  → Splash animates
  → onSplashFinished
  → if tokenStore.hasSession(): UserRepository.me()
       ├─ Outcome.Success     → show Admin/User dashboard directly
       └─ otherwise           → tokenStore.clear() + showLogin()
  → else: route via onboarding → login
```

Net effect: returning users with a valid token go **directly to their
dashboard**, never see the login screen unless their session is invalid.

---

## 4. Implementation verification

The following are wired and shipped:

- ✅ `DurableOutboundQueue` is the production implementation (wired in
  `AppGraph.outboundQueue`).
- ✅ `OkHttpRealtimeGateway` uses the `OutboundQueue` interface, so it
  works with either backing.
- ✅ Session rehydration: `RootNode.tryRehydrateSession()` runs after the
  splash animation when a token exists.
- ✅ WS 401 → refresh → reconnect: `AppGraph.refreshSessionForWebSocket`
  is wired as the gateway's `onAuthRetry` callback.

The following are documented and tracked but not yet implemented:

- ⚠️ Foreground service that holds the process alive across trigger.
- ⚠️ Server-side replay cursor for reconnect.
- ⚠️ Queue length cap with overflow eviction.
- ⚠️ Lock snapshot until first successful flush of next session.

All tracked in [MVP_COMPLETION_CHECKLIST.md](MVP_COMPLETION_CHECKLIST.md).
