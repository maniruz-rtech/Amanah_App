package com.amanah.feature.core.realtime

import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * Periodic ping + dead-server detection.
 *
 * Behaviour:
 *   - Every [pingPeriodSeconds] seconds, invokes [onPing] (gateway sends a
 *     `ping` envelope).
 *   - If no `pong` arrives within [pongTimeoutSeconds], invokes [onDead]
 *     (gateway tears down the socket and enters Reconnecting).
 *
 * The scheduler does not own the socket. It only times out based on what
 * the gateway tells it via [recordPong].
 *
 * Defaults match common WebSocket idle limits (Cloudflare 100s, AWS ALB 60s);
 * 25s + 10s leaves margin while keeping reconnect-after-drop under 35s.
 */
class HeartbeatScheduler(
    private val executor: ScheduledExecutorService,
    private val pingPeriodSeconds: Long = 25,
    private val pongTimeoutSeconds: Long = 10,
    private val onPing: () -> Unit,
    private val onDead: () -> Unit,
) {

    @Volatile private var lastPongMs: Long = 0L
    @Volatile private var pingTask: ScheduledFuture<*>? = null
    @Volatile private var watchdogTask: ScheduledFuture<*>? = null

    fun start() {
        stop()
        lastPongMs = System.currentTimeMillis()

        pingTask = executor.scheduleWithFixedDelay(
            ::doPing,
            pingPeriodSeconds,
            pingPeriodSeconds,
            TimeUnit.SECONDS,
        )

        watchdogTask = executor.scheduleWithFixedDelay(
            ::checkPong,
            pingPeriodSeconds + pongTimeoutSeconds,
            pongTimeoutSeconds,
            TimeUnit.SECONDS,
        )
    }

    fun stop() {
        pingTask?.cancel(false)
        watchdogTask?.cancel(false)
        pingTask = null
        watchdogTask = null
    }

    fun recordPong() {
        lastPongMs = System.currentTimeMillis()
    }

    private fun doPing() {
        try { onPing() } catch (_: Throwable) { /* swallowed; the watchdog will catch a stuck socket */ }
    }

    private fun checkPong() {
        val now = System.currentTimeMillis()
        val staleMs = now - lastPongMs
        val limitMs = (pingPeriodSeconds + pongTimeoutSeconds) * 1_000L
        if (staleMs > limitMs) {
            stop()
            onDead()
        }
    }
}
