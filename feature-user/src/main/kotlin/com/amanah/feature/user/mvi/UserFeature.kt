package com.amanah.feature.user.mvi

import com.amanah.feature.auth.model.AuthenticatedUser
import com.badoo.mvicore.element.Actor
import com.badoo.mvicore.element.Bootstrapper
import com.badoo.mvicore.element.NewsPublisher
import com.badoo.mvicore.element.Reducer
import com.badoo.mvicore.feature.BaseFeature
import io.reactivex.Observable

// ── Domain types ───────────────────────────────────────────────────────────────

data class NearbyUser(
    val userId: String,
    val displayName: String,
    val lat: Double,           // always obfuscated in idle state
    val lng: Double,
    val h3Cell: String,
    val isExact: Boolean = false,  // true only during active emergency
)

data class AlertSummary(
    val alertId: String,
    val triggeredAt: Long,
    val statusLabel: String,
    val wasResponder: Boolean,
)

/**
 * Responder position model used by [ResponderMapView] to place and update
 * markers on the emergency map.
 *
 * [distanceMeters] is pre-rounded to the nearest 100 m by the engine
 * before being stored here — never display a raw Haversine value in the UI.
 */
data class ResponderInfo(
    val responderId: String,
    val lat: Double,
    val lng: Double,
    val etaSeconds: Int?,
    val distanceMeters: Int?,  // nearest 100 m; null until first ETA update
)

// ── State ──────────────────────────────────────────────────────────────────────

data class UserState(
    val currentUser: AuthenticatedUser? = null,
    val tab: Tab = Tab.HOME,
    val nearbyUsers: List<NearbyUser> = emptyList(),
    val alertHistory: List<AlertSummary> = emptyList(),
    val emergencyActive: Boolean = false,
    val emergencyAlertId: String? = null,
    val victimLat: Double? = null,
    val victimLng: Double? = null,
    val victimH3Cell: String? = null,         // resolution 7 district cell
    val responders: List<ResponderInfo> = emptyList(),
    val responderEtaSeconds: Int? = null,     // nearest responder ETA
    val responderDistanceMeters: Int? = null, // nearest responder distance, pre-rounded
    val isLoadingNearby: Boolean = false,
    val isDarkMode: Boolean = false,
    val error: String? = null,
) {
    enum class Tab { HOME, ALERTS, PROFILE, SETTINGS }
}

// ── Wish ───────────────────────────────────────────────────────────────────────

sealed class UserWish {
    data class Initialize(val user: AuthenticatedUser)          : UserWish()
    data class SelectTab(val tab: UserState.Tab)                : UserWish()
    object RefreshNearby                                        : UserWish()
    object TriggerEmergency                                     : UserWish()
    object CancelEmergency                                      : UserWish()
    data class IncomingEmergencyAlert(
        val alertId: String,
        val victimLat: Double,
        val victimLng: Double,
        val victimH3Cell: String,
    ) : UserWish()
    /** Pushed by the interactor when EmergencyFeature emits EtaAvailable news. */
    data class EtaUpdated(
        val etaSeconds: Int,
        val distanceMeters: Int,   // pre-rounded to nearest 100 m
    ) : UserWish()
    /** Pushed by the interactor on each responder location update from the engine. */
    data class UpdateResponderLocation(val info: ResponderInfo) : UserWish()

    /** Pushed by the interactor after [UserRepository.listMyActiveIncidents]. */
    data class AlertsLoaded(val alerts: List<AlertSummary>)     : UserWish()

    /** Pushed by the interactor after the backend nearby-users call. */
    data class NearbyLoaded(val users: List<NearbyUser>)        : UserWish()

    object ToggleDarkMode                                       : UserWish()
    object Logout                                               : UserWish()
}

// ── Effect ─────────────────────────────────────────────────────────────────────

sealed class UserEffect {
    data class Initialized(val user: AuthenticatedUser)         : UserEffect()
    data class TabSelected(val tab: UserState.Tab)              : UserEffect()
    object NearbyLoading                                        : UserEffect()
    data class NearbyLoaded(val users: List<NearbyUser>)        : UserEffect()
    object EmergencyTriggered                                   : UserEffect()
    data class EmergencyConfirmed(val alertId: String)          : UserEffect()
    object EmergencyCancelled                                   : UserEffect()
    data class IncomingAlert(
        val alertId: String,
        val victimLat: Double,
        val victimLng: Double,
        val victimH3Cell: String,
    ) : UserEffect()
    data class EtaUpdated(val etaSeconds: Int, val distanceMeters: Int)  : UserEffect()
    data class ResponderPositionUpdated(val info: ResponderInfo)         : UserEffect()
    data class AlertsLoadedEffect(val alerts: List<AlertSummary>)        : UserEffect()
    data class DarkModeToggled(val enabled: Boolean)                     : UserEffect()
}

// ── News ───────────────────────────────────────────────────────────────────────

sealed class UserNews {
    object EmergencyTriggered                                   : UserNews()
    data class IncomingEmergency(
        val alertId: String,
        val victimLat: Double,
        val victimLng: Double,
    ) : UserNews()
    object Logout                                               : UserNews()
}

// ── Actor ──────────────────────────────────────────────────────────────────────

private class UserActor : Actor<UserState, UserWish, UserEffect> {

    override fun invoke(state: UserState, wish: UserWish): Observable<out UserEffect> =
        when (wish) {
            is UserWish.Initialize    -> Observable.just(UserEffect.Initialized(wish.user))
            is UserWish.SelectTab     -> Observable.just(UserEffect.TabSelected(wish.tab))
            is UserWish.ToggleDarkMode -> Observable.just(UserEffect.DarkModeToggled(!state.isDarkMode))
            // `RefreshNearby` is now just a loading-pulse marker; the interactor
            // calls UserRepository directly and pushes the result back via
            // [UserWish.NearbyLoaded].
            UserWish.RefreshNearby    -> Observable.just(UserEffect.NearbyLoading)
            UserWish.TriggerEmergency -> Observable.just(UserEffect.EmergencyTriggered)
            UserWish.CancelEmergency  -> Observable.just(UserEffect.EmergencyCancelled)
            is UserWish.IncomingEmergencyAlert -> Observable.just(
                UserEffect.IncomingAlert(wish.alertId, wish.victimLat, wish.victimLng, wish.victimH3Cell)
            )
            is UserWish.EtaUpdated -> Observable.just(
                UserEffect.EtaUpdated(wish.etaSeconds, wish.distanceMeters)
            )
            is UserWish.UpdateResponderLocation -> Observable.just(
                UserEffect.ResponderPositionUpdated(wish.info)
            )
            is UserWish.NearbyLoaded -> Observable.just(UserEffect.NearbyLoaded(wish.users))
            is UserWish.AlertsLoaded -> Observable.just(UserEffect.AlertsLoadedEffect(wish.alerts))
            UserWish.Logout -> Observable.empty() // handled via News
        }
}

// ── Reducer ────────────────────────────────────────────────────────────────────

private class UserReducer : Reducer<UserState, UserEffect> {
    override fun invoke(state: UserState, effect: UserEffect): UserState = when (effect) {
        is UserEffect.Initialized    -> state.copy(currentUser = effect.user)
        is UserEffect.TabSelected    -> state.copy(tab = effect.tab)
        UserEffect.NearbyLoading     -> state.copy(isLoadingNearby = true)
        is UserEffect.NearbyLoaded   -> state.copy(nearbyUsers = effect.users, isLoadingNearby = false)
        UserEffect.EmergencyTriggered -> state.copy(emergencyActive = true)
        is UserEffect.EmergencyConfirmed -> state.copy(emergencyAlertId = effect.alertId)
        UserEffect.EmergencyCancelled -> state.copy(
            emergencyActive          = false,
            emergencyAlertId         = null,
            victimLat                = null,
            victimLng                = null,
            victimH3Cell             = null,
            responders               = emptyList(),
            responderEtaSeconds      = null,
            responderDistanceMeters  = null,
        )
        is UserEffect.IncomingAlert  -> state.copy(
            emergencyActive  = true,
            emergencyAlertId = effect.alertId,
            victimLat        = effect.victimLat,
            victimLng        = effect.victimLng,
            victimH3Cell     = effect.victimH3Cell,
        )
        is UserEffect.EtaUpdated -> state.copy(
            responderEtaSeconds     = effect.etaSeconds,
            responderDistanceMeters = effect.distanceMeters,
        )
        is UserEffect.ResponderPositionUpdated -> state.copy(
            responders = state.responders
                .filterNot { it.responderId == effect.info.responderId } + effect.info,
        )
        is UserEffect.AlertsLoadedEffect -> state.copy(alertHistory = effect.alerts)
        is UserEffect.DarkModeToggled    -> state.copy(isDarkMode = effect.enabled)
    }
}

// ── NewsPublisher ──────────────────────────────────────────────────────────────

private class UserNewsPublisher :
    NewsPublisher<UserWish, UserEffect, UserState, UserNews> {
    override fun invoke(wish: UserWish, effect: UserEffect, state: UserState): UserNews? = when {
        effect == UserEffect.EmergencyTriggered -> UserNews.EmergencyTriggered
        effect is UserEffect.IncomingAlert ->
            UserNews.IncomingEmergency(effect.alertId, effect.victimLat, effect.victimLng)
        wish == UserWish.Logout -> UserNews.Logout
        else -> null
    }
}

// ── Feature ────────────────────────────────────────────────────────────────────

class UserFeature : BaseFeature<UserWish, UserWish, UserEffect, UserState, UserNews>(
    initialState  = UserState(),
    wishToAction  = { it },
    actor         = UserActor(),
    reducer       = UserReducer(),
    newsPublisher = UserNewsPublisher(),
    bootstrapper  = object : Bootstrapper<UserWish> {
        override fun invoke(): Observable<UserWish> = Observable.just(UserWish.RefreshNearby)
    },
)
