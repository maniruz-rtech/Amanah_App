package com.amanah.feature.core.realtime

import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner

/**
 * Bridges the process-wide foreground/background signal into the
 * [RealtimeGateway].
 *
 * Why a dedicated bridge rather than letting the gateway observe lifecycle
 * directly: the gateway is a plain class with no Android imports (apart from
 * OkHttp). Keeping the lifecycle adapter out here means the gateway is
 * unit-testable on JVM with no Robolectric harness.
 *
 * Registered in [AmanahApplication.onCreate] after [AppGraph] is built.
 */
class AppForegroundObserver(
    private val gateway: RealtimeGateway,
) : DefaultLifecycleObserver {

    fun attach() {
        ProcessLifecycleOwner.get().lifecycle.addObserver(this)
    }

    fun detach() {
        ProcessLifecycleOwner.get().lifecycle.removeObserver(this)
    }

    override fun onStart(owner: LifecycleOwner) {
        gateway.onForeground()
    }

    override fun onStop(owner: LifecycleOwner) {
        gateway.onBackground()
    }
}
