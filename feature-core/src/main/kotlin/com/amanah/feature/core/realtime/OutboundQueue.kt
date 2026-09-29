package com.amanah.feature.core.realtime

import java.util.concurrent.ConcurrentLinkedDeque

/**
 * Contract for the realtime gateway's outbound queue.
 *
 * Implementations:
 *   - [InMemoryOutboundQueue] — `ConcurrentLinkedDeque`-backed; used in
 *     tests and previews. Process death wipes the queue.
 *   - [DurableOutboundQueue]  — Jetpack DataStore Preferences-backed; used
 *     in production. **Survives process death and reboot.** This is the
 *     production choice for emergency-critical reliability.
 *
 * Drain semantics: each call atomically consumes the queue and returns a
 * partition of envelopes that are still within TTL (live) vs. expired.
 */
interface OutboundQueue {

    fun enqueue(envelope: RealtimeEnvelope)

    fun drainEligible(nowMs: Long = System.currentTimeMillis()): Drain

    fun isEmpty(): Boolean

    fun size(): Int

    /** Drop everything — called on disconnect-with-no-resume (e.g. logout). */
    fun clear()

    data class Drain(
        val live: List<RealtimeEnvelope>,
        val expired: List<String>,
    )
}

/**
 * In-memory FIFO. Lost on process death — only suitable for tests and
 * previews. Production code must use [DurableOutboundQueue].
 */
class InMemoryOutboundQueue : OutboundQueue {

    private data class Entry(
        val envelope: RealtimeEnvelope,
        val enqueuedAtMs: Long,
    )

    private val deque = ConcurrentLinkedDeque<Entry>()

    override fun enqueue(envelope: RealtimeEnvelope) {
        deque.addLast(Entry(envelope, System.currentTimeMillis()))
    }

    override fun drainEligible(nowMs: Long): OutboundQueue.Drain {
        val live    = mutableListOf<RealtimeEnvelope>()
        val expired = mutableListOf<String>()
        while (true) {
            val entry = deque.pollFirst() ?: break
            val ttl = entry.envelope.ttlMs
            val expiresAtMs = if (ttl == null) Long.MAX_VALUE else entry.enqueuedAtMs + ttl
            if (nowMs >= expiresAtMs) expired += entry.envelope.eventId
            else                      live    += entry.envelope
        }
        return OutboundQueue.Drain(live, expired)
    }

    override fun isEmpty(): Boolean = deque.isEmpty()
    override fun size(): Int = deque.size
    override fun clear() = deque.clear()
}
