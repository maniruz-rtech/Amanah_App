package com.amanah.feature.core.realtime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InMemoryOutboundQueueTest {

    private fun envelope(id: String, ttlMs: Long? = null) = RealtimeEnvelope(
        type        = EventTypes.PRESENCE,
        eventId     = id,
        timestampMs = System.currentTimeMillis(),
        ttlMs       = ttlMs,
    )

    @Test fun `drain returns enqueued items in FIFO order`() {
        val q = InMemoryOutboundQueue()
        q.enqueue(envelope("a"))
        q.enqueue(envelope("b"))
        q.enqueue(envelope("c"))

        val drain = q.drainEligible()
        assertEquals(listOf("a", "b", "c"), drain.live.map { it.eventId })
        assertTrue(drain.expired.isEmpty())
        assertTrue(q.isEmpty())
    }

    @Test fun `expired items move to expired list`() {
        val q = InMemoryOutboundQueue()
        // Enqueue with a TTL that has already elapsed (-1 ms ago).
        q.enqueue(envelope("stale", ttlMs = -1L))
        q.enqueue(envelope("fresh", ttlMs = 60_000L))

        val drain = q.drainEligible(nowMs = System.currentTimeMillis())
        assertEquals(listOf("fresh"), drain.live.map { it.eventId })
        assertEquals(listOf("stale"), drain.expired)
    }

    @Test fun `clear empties the queue`() {
        val q = InMemoryOutboundQueue()
        q.enqueue(envelope("x"))
        q.clear()
        assertTrue(q.isEmpty())
        assertEquals(0, q.size())
    }

    @Test fun `drain on empty queue yields empty partition`() {
        val q = InMemoryOutboundQueue()
        val drain = q.drainEligible()
        assertTrue(drain.live.isEmpty())
        assertTrue(drain.expired.isEmpty())
    }
}
