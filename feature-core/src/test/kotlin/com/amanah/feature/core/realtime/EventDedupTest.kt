package com.amanah.feature.core.realtime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EventDedupTest {

    @Test fun `first sighting returns true`() {
        val d = EventDedup()
        assertTrue(d.firstSeen("a"))
    }

    @Test fun `duplicate sighting returns false`() {
        val d = EventDedup()
        d.firstSeen("a")
        assertFalse(d.firstSeen("a"))
    }

    @Test fun `different ids do not collide`() {
        val d = EventDedup()
        assertTrue(d.firstSeen("a"))
        assertTrue(d.firstSeen("b"))
    }

    @Test fun `LRU evicts the oldest when capacity is exceeded`() {
        val d = EventDedup(maxEntries = 3)
        d.firstSeen("a")
        d.firstSeen("b")
        d.firstSeen("c")
        // touch 'a' to mark it MRU
        d.firstSeen("a")
        // insert 'd' — eldest ('b') should be evicted
        d.firstSeen("d")
        assertTrue("'b' should have been evicted", d.firstSeen("b"))
        assertFalse("'a' should still be present", d.firstSeen("a"))
    }

    @Test fun `clear empties the cache`() {
        val d = EventDedup()
        d.firstSeen("a")
        d.clear()
        assertTrue(d.firstSeen("a"))
        assertEquals(1, d.size())
    }
}
