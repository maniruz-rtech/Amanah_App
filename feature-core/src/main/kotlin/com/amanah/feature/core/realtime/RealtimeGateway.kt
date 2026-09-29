package com.amanah.feature.core.realtime

import com.badoo.reaktive.observable.Observable

/**
 * Single integration seam for every realtime channel in the app.
 *
 * The gateway is **explicit** — the composition root decides when to [connect]
 * and [disconnect]. There is no implicit Android-lifecycle wiring inside the
 * gateway; an external [AppForegroundObserver] feeds intent signals back via
 * [onForeground] / [onBackground] so callers can audit behaviour deterministically.
 *
 * Stream semantics:
 *   - [state] is a hot stream backed by a behavior subject: subscribers always
 *     receive the most recent [RealtimeConnectionState] on subscribe.
 *   - [incoming] is a hot stream backed by a publish subject: events that
 *     arrived before subscription are NOT replayed. Use the [AckRegistry] /
 *     [OutboundQueue] if you need durability across subscription lifetimes.
 *   - [send] is non-blocking; while the socket is offline the envelope is
 *     persisted in the [OutboundQueue] and flushed on reconnect.
 *
 * Threading: the gateway never blocks the caller. All I/O lives inside the
 * implementation; subscribers receive events on Reaktive's mainScheduler.
 */
interface RealtimeGateway {

    /** Hot stream of connection state. Replays the latest value to new subscribers. */
    val state: Observable<RealtimeConnectionState>

    /** Hot stream of inbound, deduplicated, ordered events. */
    val incoming: Observable<RealtimeEvent>

    /**
     * Establishes the WebSocket connection. Safe to call multiple times — extra
     * calls are coalesced into a single live socket. The auth token is read
     * from the supplied [TokenProvider] **at handshake time only** (not stored
     * in the URL).
     */
    fun connect()

    /**
     * Tears down the active socket cleanly and drains the outbound queue.
     * The gateway stops trying to reconnect until [connect] is called again.
     */
    fun disconnect()

    /**
     * Enqueues an outbound envelope. If the socket is online and the queue is
     * empty, the envelope is transmitted immediately. Otherwise it is stored
     * durably and flushed in arrival order on next reconnect.
     *
     * Returns a server-confirmation observable that:
     *   - emits [SendOutcome.Acknowledged] once the server ACKs the envelope's
     *     [RealtimeEnvelope.eventId];
     *   - emits [SendOutcome.Failed] if the message expires from the queue
     *     (e.g. TTL exceeded) before an ACK arrives.
     *
     * The observable completes after one emission; subscribers may receive
     * the outcome on the main thread.
     */
    fun send(envelope: RealtimeEnvelope): Observable<SendOutcome>

    /** Lifecycle hook fed by [AppForegroundObserver]. */
    fun onForeground()
    fun onBackground()
}

/** Thin token provider so the gateway never holds tokens at construction time. */
fun interface TokenProvider {
    /** Returns the current access token or null if no session is active. */
    fun current(): String?
}

/** Outcome of a [RealtimeGateway.send] call. */
sealed class SendOutcome {
    /** Server accepted the envelope and emitted an ACK for [eventId]. */
    data class Acknowledged(val eventId: String) : SendOutcome()

    /** Envelope expired in the outbound queue without an ACK. */
    data class Failed(val eventId: String, val reason: String) : SendOutcome()
}
