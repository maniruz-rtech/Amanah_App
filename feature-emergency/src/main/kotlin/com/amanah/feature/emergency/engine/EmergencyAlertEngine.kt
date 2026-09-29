package com.amanah.feature.emergency.engine

import com.amanah.feature.core.repository.Outcome
import com.amanah.feature.emergency.model.EmergencyAlertMessage
import com.amanah.feature.emergency.model.EmergencyAlertStatus
import com.amanah.feature.emergency.mvi.EmergencyFeature
import com.amanah.feature.emergency.mvi.EmergencyNews
import com.amanah.feature.emergency.mvi.EmergencyState
import com.amanah.feature.emergency.mvi.EmergencyWish
import com.amanah.feature.emergency.proximity.ProximityMatcher
import com.amanah.feature.emergency.repository.EmergencyRepository
import com.amanah.lib.location.H3LocationIndex
import com.amanah.lib.location.H3Resolution
import com.amanah.lib.location.LocationPrivacyFilter
import io.reactivex.Observable
import io.reactivex.disposables.CompositeDisposable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Coordinates the emergency-alert lifecycle on the client side.
 *
 *   • Outbound (this device is the victim)
 *     - [triggerAlert] hands off to the MVI feature; the resulting
 *       BroadcastEmergency news fires a **REST** call to /api/v1/incidents/sos
 *       via [emergencyRepository]. The REST response is the canonical alert
 *       record. The WebSocket is NOT used for the trigger — the server fans
 *       the alert out to nearby clients after persistence.
 *     - [cancelAlert] similarly hits POST /incidents/{id}/cancel.
 *
 *   • Inbound (this device is a potential responder)
 *     - [onIncomingAlert] receives the server-broadcast WebSocket envelope
 *       and gates via [ProximityMatcher]. Exact victim coordinates are
 *       forwarded only when status == ACTIVE (privacy boundary).
 *     - [onResponderLocationUpdate] receives responder updates from the
 *       realtime layer and surfaces them on the victim's UI.
 *
 * Resilience: the [emergencyRepository] handles its own retry/backoff. On a
 * terminal failure (auth, validation, or exhausted retries) the engine emits
 * [EmergencyWish.AlertError] so the UI can surface a hard error.
 */
class EmergencyAlertEngine(
    private val feature: EmergencyFeature,
    private val emergencyRepository: EmergencyRepository,
    private val currentUserId: String,
    private val currentUserH3Cell: String,
    private val onEtaAvailable: (etaSeconds: Int, distanceMeters: Int) -> Unit = { _, _ -> },
    private val onResponderUpdate: (responderId: String, lat: Double, lng: Double,
                                    etaSeconds: Int?, distanceMeters: Int) -> Unit = { _, _, _, _, _ -> },
    private val onAlertPersisted: (alertId: String) -> Unit = { _ -> },
    private val onAlertError: (message: String) -> Unit = { _ -> },
) {
    private val disposables = CompositeDisposable()
    private val ioScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    // Kept in sync with feature.states so we can read current state synchronously
    // in publishCancellation() without requiring a blocking Observable.blockingFirst().
    private var cachedState: EmergencyState = EmergencyState()

    fun start() {
        disposables.add(
            Observable.wrap(feature).subscribe { state -> cachedState = state }
        )
        disposables.add(
            Observable.wrap(feature.news).subscribe { news ->
                when (news) {
                    is EmergencyNews.BroadcastEmergency -> persistAlertViaRest(news)
                    EmergencyNews.AlertCancelled        -> cancelViaRest()
                    is EmergencyNews.EtaAvailable       ->
                        onEtaAvailable(news.etaSeconds, news.distanceMeters)
                    EmergencyNews.AlertResolved         -> { /* server-side resolution */ }
                }
            }
        )
    }

    fun stop() {
        disposables.clear()
        ioScope.cancel()
    }

    // ── Outbound (victim triggers / cancels alert) ────────────────────────────

    fun triggerAlert(lat: Double, lng: Double) {
        feature.accept(EmergencyWish.TriggerAlert(lat, lng, currentUserId))
    }

    fun cancelAlert() {
        feature.accept(EmergencyWish.CancelAlert)
    }

    // ── Inbound: server sends emergency alert message ────────────────────────

    fun onIncomingAlert(message: EmergencyAlertMessage) {
        when (message.status) {
            EmergencyAlertStatus.ACTIVE -> {
                val inRange = ProximityMatcher.isResponderInRange(
                    victimH3Cell    = message.h3Cell,
                    responderH3Cell = currentUserH3Cell,
                    kRings          = message.kRing,
                )
                if (inRange) {
                    feature.accept(
                        EmergencyWish.AlertConfirmed(
                            alertId   = message.alertId,
                            h3Cell    = message.h3Cell,
                            victimLat = message.lat,
                            victimLng = message.lng,
                        )
                    )
                }
            }
            EmergencyAlertStatus.RESOLVED,
            EmergencyAlertStatus.CANCELLED,
            EmergencyAlertStatus.TIMED_OUT -> feature.accept(EmergencyWish.ResolveAlert)
        }
    }

    // ── Inbound: responder sends location update ─────────────────────────────

    fun onResponderLocationUpdate(
        responderId: String,
        alertId: String,
        lat: Double,
        lng: Double,
        etaSeconds: Int?,
        timestampMs: Long,
    ) {
        if (!cachedState.isActiveEmergency) return
        val victimLat = cachedState.victimLat ?: return
        val victimLng = cachedState.victimLng ?: return

        val rawDistanceMeters = LocationPrivacyFilter
            .haversineMeters(victimLat, victimLng, lat, lng)
            .toInt()

        val roundedDistanceMeters = LocationPrivacyFilter.roundToNearest100m(rawDistanceMeters)

        feature.accept(
            EmergencyWish.ResponderUpdate(
                com.amanah.feature.emergency.model.ResponderLocationUpdate(
                    responderId = responderId,
                    alertId     = alertId,
                    lat         = lat,
                    lng         = lng,
                    etaSeconds  = etaSeconds,
                    timestamp   = timestampMs,
                )
            )
        )

        if (etaSeconds != null) {
            feature.accept(EmergencyWish.EtaReceived(responderId, etaSeconds, rawDistanceMeters))
            feature.accept(EmergencyWish.ResponderAccepted(responderId))
        }

        onResponderUpdate(
            responderId,
            lat,
            lng,
            etaSeconds,
            roundedDistanceMeters,
        )
    }

    // ── REST persistence (THIS is the canonical persistence path) ─────────────

    private fun persistAlertViaRest(news: EmergencyNews.BroadcastEmergency) {
        ioScope.launch {
            val outcome = emergencyRepository.createSos(
                lat    = news.lat,
                lng    = news.lng,
                h3Cell = news.h3Cell,
                // severity/incidentType default to HIGH/SOS on the server
            )
            when (outcome) {
                is Outcome.Success -> {
                    val incident = outcome.value
                    // Confirm the alert in the local FSM with the SERVER-assigned id.
                    feature.accept(
                        EmergencyWish.AlertConfirmed(
                            alertId   = incident.id,
                            h3Cell    = incident.h3Cell ?: news.h3Cell,
                            victimLat = news.lat,
                            victimLng = news.lng,
                        )
                    )
                    onAlertPersisted(incident.id)
                }
                Outcome.AuthFailed -> {
                    feature.accept(EmergencyWish.AlertError("Please sign in again"))
                    onAlertError("auth_required")
                }
                Outcome.NetworkDown -> {
                    feature.accept(EmergencyWish.AlertError("No network — retry when online"))
                    onAlertError("network_down")
                }
                is Outcome.ServerError -> {
                    feature.accept(EmergencyWish.AlertError("Server error (${outcome.code})"))
                    onAlertError("server_${outcome.code}")
                }
                is Outcome.Unexpected -> {
                    feature.accept(EmergencyWish.AlertError("Unexpected failure"))
                    onAlertError("unexpected")
                }
            }
        }
    }

    private fun cancelViaRest() {
        val alertId = cachedState.activeAlertId ?: return
        ioScope.launch {
            val outcome = emergencyRepository.cancel(
                incidentId = alertId,
                reason     = "user_cancelled",
            )
            if (outcome !is Outcome.Success) {
                // Cancellation failed; surface but the local FSM has already
                // transitioned to IDLE so we don't try to revert.
                onAlertError("cancel_failed")
            }
        }
    }
}
