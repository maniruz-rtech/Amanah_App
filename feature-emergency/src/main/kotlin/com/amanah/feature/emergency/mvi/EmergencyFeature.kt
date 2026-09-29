package com.amanah.feature.emergency.mvi

import com.amanah.feature.emergency.model.EmergencyAlertStatus
import com.amanah.feature.emergency.model.ResponderLocationUpdate
import com.amanah.lib.location.H3LocationIndex
import com.amanah.lib.location.H3Resolution
import com.amanah.lib.location.LocationPrivacyFilter
import com.badoo.mvicore.element.Actor
import com.badoo.mvicore.element.NewsPublisher
import com.badoo.mvicore.element.Reducer
import com.badoo.mvicore.feature.BaseFeature
import io.reactivex.Observable

// ── State ──────────────────────────────────────────────────────────────────────

data class EmergencyState(
    val phase: Phase = Phase.IDLE,
    val activeAlertId: String? = null,
    val victimLat: Double? = null,
    val victimLng: Double? = null,
    val victimH3Cell: String? = null,
    val victimH3CellBlock: String? = null,       // resolution 9 — precise dispatch
    val responders: List<ResponderLocationUpdate> = emptyList(),
    val nearbyCount: Int = 0,
    val nearestEtaSeconds: Int? = null,
    val nearestDistanceMeters: Int? = null,       // rounded to nearest 100 m
    val enRouteResponderIds: Set<String> = emptySet(),
    val error: String? = null,
) {
    /**
     * Emergency lifecycle phases (strict state machine):
     *
     *   IDLE ──TriggerAlert──► BROADCASTING
     *   BROADCASTING ──AlertConfirmed──► CALCULATING_ETA
     *   CALCULATING_ETA ──MarkVictimLocated──► VICTIM_LOCATED
     *   VICTIM_LOCATED ──ResponderAccepted──► RESPONDER_EN_ROUTE
     *   CALCULATING_ETA | VICTIM_LOCATED | RESPONDER_EN_ROUTE
     *       ──Resolve/Cancel──► IDLE
     *   Any ──Error──► IDLE
     *
     *  [ACTIVE_EMERGENCY] kept for wire-compat; treated identically to
     *  [RESPONDER_EN_ROUTE] in all privacy and safety checks.
     */
    enum class Phase {
        IDLE,
        BROADCASTING,           // alert sent; awaiting server geo-shard ACK
        CALCULATING_ETA,        // server ACK received; computing responder ETAs
        VICTIM_LOCATED,         // victim pinned on map; no responder en route yet
        RESPONDER_EN_ROUTE,     // ≥1 responder accepted + actively routing
        ACTIVE_EMERGENCY,       // wire-compat alias — same semantics as RESPONDER_EN_ROUTE
    }

    /** True for any phase where exact victim GPS may be surfaced in the UI. */
    val isActiveEmergency: Boolean
        get() = phase in setOf(
            Phase.ACTIVE_EMERGENCY,
            Phase.CALCULATING_ETA,
            Phase.VICTIM_LOCATED,
            Phase.RESPONDER_EN_ROUTE,
        )
}

// ── Wish ───────────────────────────────────────────────────────────────────────

sealed class EmergencyWish {
    data class TriggerAlert(val lat: Double, val lng: Double, val userId: String) : EmergencyWish()

    /** Server confirmed the alert; carries exact victim coordinates for map pin. */
    data class AlertConfirmed(
        val alertId: String,
        val h3Cell: String,
        val victimLat: Double,
        val victimLng: Double,
    ) : EmergencyWish()

    data class ResponderUpdate(val update: ResponderLocationUpdate)                : EmergencyWish()

    /** Fired by the map composable once the victim marker finishes rendering. */
    object MarkVictimLocated                                                      : EmergencyWish()

    /** Fired when a responder's location update carries ETA data for the first time. */
    data class EtaReceived(
        val responderId: String,
        val etaSeconds: Int,
        val distanceMeters: Int,    // raw metres — reduced to nearest 100 m in Reducer
    ) : EmergencyWish()

    /** Fired when a responder sends their first location update (acceptance signal). */
    data class ResponderAccepted(val responderId: String)                         : EmergencyWish()

    object ResolveAlert                                                           : EmergencyWish()
    object CancelAlert                                                            : EmergencyWish()
    data class AlertError(val message: String)                                    : EmergencyWish()
}

// ── Effect ─────────────────────────────────────────────────────────────────────

sealed class EmergencyEffect {
    data class BroadcastStarted(
        val lat: Double, val lng: Double, val userId: String,
    ) : EmergencyEffect()

    data class AlertConfirmed(
        val alertId: String,
        val h3Cell: String,
        val h3CellBlock: String,     // resolution 9 computed by Actor
        val victimLat: Double,
        val victimLng: Double,
    ) : EmergencyEffect()

    data class ResponderAdded(val update: ResponderLocationUpdate)               : EmergencyEffect()
    object VictimPinned                                                          : EmergencyEffect()

    data class EtaCalculated(
        val responderId: String,
        val etaSeconds: Int,
        val distanceMeters: Int,     // raw — Reducer rounds this
    ) : EmergencyEffect()

    data class ResponderRouting(val responderId: String)                         : EmergencyEffect()
    object AlertEnded                                                            : EmergencyEffect()
    data class ErrorOccurred(val message: String)                               : EmergencyEffect()
}

// ── News ───────────────────────────────────────────────────────────────────────

sealed class EmergencyNews {
    data class BroadcastEmergency(
        val lat: Double, val lng: Double, val h3Cell: String, val userId: String,
    ) : EmergencyNews()

    /** Published whenever the nearest responder's ETA improves (decreases). */
    data class EtaAvailable(
        val etaSeconds: Int,
        val distanceMeters: Int,     // already rounded to nearest 100 m
    ) : EmergencyNews()

    object AlertCancelled : EmergencyNews()
    object AlertResolved  : EmergencyNews()
}

// ── Actor ──────────────────────────────────────────────────────────────────────

private class EmergencyActor : Actor<EmergencyState, EmergencyWish, EmergencyEffect> {

    override fun invoke(state: EmergencyState, wish: EmergencyWish): Observable<out EmergencyEffect> =
        when (wish) {
            is EmergencyWish.TriggerAlert -> {
                if (state.phase != EmergencyState.Phase.IDLE) Observable.empty()
                else Observable.just(EmergencyEffect.BroadcastStarted(wish.lat, wish.lng, wish.userId))
            }

            is EmergencyWish.AlertConfirmed -> {
                // Encode the block-level (res 9) H3 cell for precise dispatch —
                // the district-level cell (res 7) already arrived from the server.
                val blockCell = H3LocationIndex.encode(wish.victimLat, wish.victimLng, H3Resolution.BLOCK)
                Observable.just(
                    EmergencyEffect.AlertConfirmed(
                        alertId      = wish.alertId,
                        h3Cell       = wish.h3Cell,
                        h3CellBlock  = blockCell,
                        victimLat    = wish.victimLat,
                        victimLng    = wish.victimLng,
                    )
                )
            }

            is EmergencyWish.ResponderUpdate ->
                Observable.just(EmergencyEffect.ResponderAdded(wish.update))

            EmergencyWish.MarkVictimLocated ->
                if (state.isActiveEmergency) Observable.just(EmergencyEffect.VictimPinned)
                else Observable.empty()

            is EmergencyWish.EtaReceived ->
                if (state.isActiveEmergency)
                    Observable.just(EmergencyEffect.EtaCalculated(wish.responderId, wish.etaSeconds, wish.distanceMeters))
                else Observable.empty()

            is EmergencyWish.ResponderAccepted ->
                if (state.isActiveEmergency)
                    Observable.just(EmergencyEffect.ResponderRouting(wish.responderId))
                else Observable.empty()

            EmergencyWish.ResolveAlert, EmergencyWish.CancelAlert ->
                Observable.just(EmergencyEffect.AlertEnded)

            is EmergencyWish.AlertError ->
                Observable.just(EmergencyEffect.ErrorOccurred(wish.message))
        }
}

// ── Reducer ────────────────────────────────────────────────────────────────────

private class EmergencyReducer : Reducer<EmergencyState, EmergencyEffect> {
    override fun invoke(state: EmergencyState, effect: EmergencyEffect): EmergencyState =
        when (effect) {
            is EmergencyEffect.BroadcastStarted -> state.copy(
                phase     = EmergencyState.Phase.BROADCASTING,
                victimLat = effect.lat,
                victimLng = effect.lng,
                error     = null,
            )

            is EmergencyEffect.AlertConfirmed -> state.copy(
                phase             = EmergencyState.Phase.CALCULATING_ETA,
                activeAlertId     = effect.alertId,
                victimH3Cell      = effect.h3Cell,
                victimH3CellBlock = effect.h3CellBlock,
                victimLat         = effect.victimLat,
                victimLng         = effect.victimLng,
            )

            is EmergencyEffect.ResponderAdded -> state.copy(
                responders = state.responders
                    .filterNot { it.responderId == effect.update.responderId } + effect.update,
            )

            EmergencyEffect.VictimPinned -> state.copy(
                phase = if (state.enRouteResponderIds.isEmpty())
                    EmergencyState.Phase.VICTIM_LOCATED
                else
                    state.phase,
            )

            is EmergencyEffect.EtaCalculated -> {
                val rounded = LocationPrivacyFilter.roundToNearest100m(effect.distanceMeters)
                val isNearer = state.nearestEtaSeconds == null ||
                        effect.etaSeconds < state.nearestEtaSeconds
                state.copy(
                    nearestEtaSeconds     = if (isNearer) effect.etaSeconds else state.nearestEtaSeconds,
                    nearestDistanceMeters = if (isNearer) rounded else state.nearestDistanceMeters,
                )
            }

            is EmergencyEffect.ResponderRouting -> state.copy(
                phase               = EmergencyState.Phase.RESPONDER_EN_ROUTE,
                enRouteResponderIds = state.enRouteResponderIds + effect.responderId,
            )

            EmergencyEffect.AlertEnded -> EmergencyState()

            is EmergencyEffect.ErrorOccurred -> state.copy(
                phase = EmergencyState.Phase.IDLE,
                error = effect.message,
            )
        }
}

// ── NewsPublisher ──────────────────────────────────────────────────────────────

private class EmergencyNewsPublisher :
    NewsPublisher<EmergencyWish, EmergencyEffect, EmergencyState, EmergencyNews> {

    override fun invoke(
        wish: EmergencyWish,
        effect: EmergencyEffect,
        state: EmergencyState,
    ): EmergencyNews? = when {

        effect is EmergencyEffect.BroadcastStarted -> {
            val h3 = H3LocationIndex.encode(effect.lat, effect.lng, H3Resolution.DISTRICT)
            EmergencyNews.BroadcastEmergency(effect.lat, effect.lng, h3, effect.userId)
        }

        // Publish EtaAvailable only when the new reading is strictly better than the
        // current nearest — prevents flooding subscribers with non-improving updates.
        effect is EmergencyEffect.EtaCalculated &&
                (state.nearestEtaSeconds == null ||
                        effect.etaSeconds <= state.nearestEtaSeconds) -> {
            val rounded = LocationPrivacyFilter.roundToNearest100m(effect.distanceMeters)
            EmergencyNews.EtaAvailable(effect.etaSeconds, rounded)
        }

        wish == EmergencyWish.CancelAlert  -> EmergencyNews.AlertCancelled
        wish == EmergencyWish.ResolveAlert -> EmergencyNews.AlertResolved

        else -> null
    }
}

// ── Feature ────────────────────────────────────────────────────────────────────

class EmergencyFeature : BaseFeature<EmergencyWish, EmergencyWish, EmergencyEffect, EmergencyState, EmergencyNews>(
    initialState  = EmergencyState(),
    wishToAction  = { it },
    actor         = EmergencyActor(),
    reducer       = EmergencyReducer(),
    newsPublisher = EmergencyNewsPublisher(),
)
