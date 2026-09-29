package com.amanah.feature.core.realtime

import kotlin.math.min
import kotlin.random.Random
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds

/**
 * Pure, testable reconnect-delay calculator.
 *
 * Behaviour:
 *   - Truncated exponential backoff with full jitter (per AWS Architecture Blog).
 *   - Schedule: 1s, 2s, 5s, 10s, 30s, 60s (capped).
 *   - Full jitter: returns `random(0, schedule[i])`. Prevents thundering-herd
 *     reconnects after server-side restarts.
 *
 * Why a custom curve instead of `1s * 2^attempt`:
 *   Emergency reconnects in the first 10s matter the most (the user might be
 *   actively triggering an SOS). The early schedule is denser than a pure
 *   exponential would give us.
 *
 * No state lives inside the strategy — it is a pure function. The gateway
 * passes the current `attempt` count from its FSM.
 */
class ReconnectStrategy(
    private val random: Random = Random.Default,
) {

    fun delayFor(attempt: Int): Duration {
        val capped = min(attempt, SCHEDULE.lastIndex).coerceAtLeast(0)
        val ceiling = SCHEDULE[capped]
        val jitterMs = random.nextLong(0L, ceiling.inWholeMilliseconds + 1)
        return jitterMs.milliseconds
    }

    /** Treat a 5-minute streak of failed reconnects as terminal. */
    fun shouldGiveUp(attempt: Int, totalElapsed: Duration): Boolean =
        attempt >= MAX_ATTEMPTS || totalElapsed >= MAX_TOTAL

    companion object {
        val SCHEDULE = listOf(
            1.seconds,
            2.seconds,
            5.seconds,
            10.seconds,
            30.seconds,
            60.seconds,
        )

        const val MAX_ATTEMPTS = 30
        val MAX_TOTAL: Duration = 30.seconds * 60   // 30 minutes
    }
}
