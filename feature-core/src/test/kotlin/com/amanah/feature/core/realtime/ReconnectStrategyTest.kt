package com.amanah.feature.core.realtime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds

/**
 * Pure-function tests for [ReconnectStrategy]. No coroutines, no Android.
 * Each schedule slot is verified with a seeded RNG so the full-jitter
 * formula is deterministic.
 */
class ReconnectStrategyTest {

    @Test fun `delay slot 0 is bounded by 1 second`() {
        val s = ReconnectStrategy(random = Random(0))
        repeat(20) {
            val d = s.delayFor(attempt = 0)
            assertTrue("expected ≤ 1s, got $d", d <= 1.seconds)
        }
    }

    @Test fun `delay slot 1 is bounded by 2 seconds`() {
        val s = ReconnectStrategy(random = Random(0))
        repeat(20) { assertTrue(s.delayFor(1) <= 2.seconds) }
    }

    @Test fun `delay slot 5 is bounded by 60 seconds`() {
        val s = ReconnectStrategy(random = Random(0))
        repeat(20) { assertTrue(s.delayFor(5) <= 60.seconds) }
    }

    @Test fun `delay above last slot caps at the final entry`() {
        val s = ReconnectStrategy(random = Random(0))
        val capped = s.delayFor(attempt = 999)
        assertTrue("expected ≤ 60s, got $capped", capped <= 60.seconds)
    }

    @Test fun `gives up after MAX_ATTEMPTS`() {
        val s = ReconnectStrategy()
        assertTrue(s.shouldGiveUp(attempt = ReconnectStrategy.MAX_ATTEMPTS, totalElapsed = 1.minutes))
        assertFalse(s.shouldGiveUp(attempt = 5, totalElapsed = 1.minutes))
    }

    @Test fun `gives up after total elapsed exceeds 30 minutes`() {
        val s = ReconnectStrategy()
        assertTrue(s.shouldGiveUp(attempt = 3, totalElapsed = 31.minutes))
    }

    @Test fun `negative attempt is treated as zero`() {
        val s = ReconnectStrategy(random = Random(0))
        val d = s.delayFor(attempt = -42)
        assertTrue("expected ≤ 1s for negative input, got $d", d <= 1.seconds)
    }

    @Test fun `schedule has six bounded slots in ascending order`() {
        val sched = ReconnectStrategy.SCHEDULE
        assertEquals(6, sched.size)
        for (i in 1 until sched.size) {
            assertTrue("schedule not ascending at $i", sched[i] >= sched[i - 1])
        }
    }
}
