package com.amanah.feature.core.realtime

import kotlin.time.Duration

/**
 * Strict state machine for the realtime connection.
 *
 *   IDLE  ──connect()────►  CONNECTING
 *   CONNECTING ─open ws──►  AUTHENTICATING
 *   AUTHENTICATING ─ack──►  ONLINE
 *   ONLINE ───lost/error─►  RECONNECTING(delay)
 *   RECONNECTING ─timer──►  CONNECTING
 *   any ──disconnect()──►   IDLE
 *
 * Each [RealtimeConnectionState] subtype is a data class so transitions can be
 * compared with `==` in tests and logged verbatim (no boolean-flag tea-leaves).
 */
sealed class RealtimeConnectionState {

    /** No connection has been requested. Initial state and post-[disconnect] state. */
    object Idle : RealtimeConnectionState()

    /** Socket is being opened. No auth handshake yet. */
    object Connecting : RealtimeConnectionState()

    /** Socket is open but the server has not yet confirmed the auth handshake. */
    object Authenticating : RealtimeConnectionState()

    /** Fully online — auth ACK received. Heartbeat is running. */
    data class Online(val sinceEpochMs: Long) : RealtimeConnectionState()

    /**
     * Connection dropped; waiting [delay] before the next attempt.
     * [attempt] is the 1-indexed try number; resets to 0 after a successful Online.
     */
    data class Reconnecting(val attempt: Int, val delay: Duration) : RealtimeConnectionState()

    /**
     * Terminal failure — the gateway has exhausted retries or hit a non-retryable
     * code (e.g. 401 — token revoked). Callers should surface a "sign in again"
     * affordance. A subsequent [RealtimeGateway.connect] resets the machine.
     */
    data class Terminated(val reason: TerminationReason) : RealtimeConnectionState()

    enum class TerminationReason {
        AUTH_REJECTED,        // server returned 401/4001 — re-login required
        TLS_FAILED,           // certificate pin or chain validation failed
        SERVER_FATAL,         // server returned a permanent error code
        USER_REQUESTED,       // disconnect() was called
    }
}
