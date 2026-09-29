package com.amanah.feature.core.ui

import com.amanah.feature.core.realtime.RealtimeConnectionState
import com.amanah.feature.core.realtime.RealtimeGateway
import com.badoo.reaktive.observable.Observable
import com.badoo.reaktive.observable.map
import com.badoo.reaktive.observable.observable
import com.badoo.reaktive.subject.behavior.BehaviorSubject

/**
 * Reduces the gateway's [RealtimeConnectionState] FSM into a simple banner
 * model the UI can subscribe to.
 *
 *   ConnectivityBannerState.Hidden     — Online: nothing to show.
 *   ConnectivityBannerState.Connecting — Connecting / Authenticating: subtle
 *                                          indicator.
 *   ConnectivityBannerState.Offline    — Reconnecting / Idle / Terminated:
 *                                          shows the offline banner with the
 *                                          retry-attempt count.
 *
 * Why this exists: the UI doesn't need the full state machine. Mapping
 * down to three banner states keeps view code simple and avoids
 * recomposition storms.
 */
sealed class ConnectivityBannerState {
    object Hidden     : ConnectivityBannerState()
    object Connecting : ConnectivityBannerState()
    data class Offline(val reason: String, val retryAttempt: Int) : ConnectivityBannerState()
}

/** Reactive projection of the gateway FSM into a banner-friendly state. */
fun RealtimeGateway.connectivityBanner(): Observable<ConnectivityBannerState> =
    state.map { s ->
        when (s) {
            RealtimeConnectionState.Idle           -> ConnectivityBannerState.Offline("idle", 0)
            RealtimeConnectionState.Connecting     -> ConnectivityBannerState.Connecting
            RealtimeConnectionState.Authenticating -> ConnectivityBannerState.Connecting
            is RealtimeConnectionState.Online      -> ConnectivityBannerState.Hidden
            is RealtimeConnectionState.Reconnecting ->
                ConnectivityBannerState.Offline("reconnecting", s.attempt)
            is RealtimeConnectionState.Terminated  ->
                ConnectivityBannerState.Offline("terminated:${s.reason}", 0)
        }
    }
