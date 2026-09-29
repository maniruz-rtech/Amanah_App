package com.amanah.feature.core.push

import com.badoo.reaktive.observable.Observable
import com.badoo.reaktive.subject.publish.PublishSubject

/**
 * Process-wide bus for FCM signals.
 *
 * Why a singleton object: the FirebaseMessagingService is instantiated by the
 * Android system, not by the app graph. We can't inject anything into it. The
 * bus is the only stable bridge between the service and the rest of the
 * application.
 *
 * Subscribers (typically the [com.amanah.app.di.AppGraph]) wire these
 * streams into their own logic:
 *   - [tokens]            → DeviceRepository.register(...)
 *   - [wakeups]            → RealtimeGateway.connect()
 *   - [incomingAlerts]    → UserDashboardInteractor.onIncomingAlert(...)
 *
 * All three streams are hot. There is at most one inbound event per FCM
 * delivery, so subscribers should not back-pressure.
 */
object PushBus {

    private val tokenSubject       = PublishSubject<String>()
    private val wakeupSubject      = PublishSubject<Unit>()
    private val incomingAlertSubject = PublishSubject<IncomingAlert>()

    val tokens:         Observable<String>          = tokenSubject
    val wakeups:        Observable<Unit>            = wakeupSubject
    val incomingAlerts: Observable<IncomingAlert>   = incomingAlertSubject

    internal fun onTokenRefreshed(token: String) {
        tokenSubject.onNext(token)
    }

    internal fun onWakeupRequested() {
        wakeupSubject.onNext(Unit)
    }

    internal fun onIncomingAlert(alertId: String, victimLat: Double?, victimLng: Double?) {
        if (alertId.isBlank()) return
        incomingAlertSubject.onNext(IncomingAlert(alertId, victimLat, victimLng))
    }

    data class IncomingAlert(
        val alertId: String,
        val victimLat: Double?,
        val victimLng: Double?,
    )
}
