package com.amanah.feature.user.node.dashboard

import com.amanah.feature.auth.model.AuthenticatedUser
import com.amanah.feature.core.debug.AmanahDebugDrawer
import com.amanah.feature.core.realtime.RealtimeEvent
import com.amanah.feature.core.realtime.RealtimeGateway
import com.amanah.feature.core.repository.Outcome
import com.amanah.feature.emergency.engine.EmergencyAlertEngine
import com.amanah.feature.emergency.model.EmergencyAlertMessage
import com.amanah.feature.emergency.model.EmergencyAlertStatus
import com.amanah.feature.emergency.mvi.EmergencyFeature
import com.amanah.feature.emergency.mvi.EmergencyState
import com.amanah.feature.emergency.repository.EmergencyRepository
import com.amanah.feature.user.mvi.AlertSummary
import com.amanah.feature.user.mvi.NearbyUser
import com.amanah.feature.user.mvi.ResponderInfo
import com.amanah.feature.user.mvi.UserFeature
import com.amanah.feature.user.mvi.UserNews
import com.amanah.feature.user.mvi.UserWish
import com.amanah.feature.user.repository.UserRepository
import com.amanah.lib.location.H3Resolution
import com.amanah.lib.nodes.Interactor
import com.badoo.reaktive.observable.subscribe
import io.reactivex.Observable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Interactor for the user dashboard.
 *
 * Owns both [UserFeature] and [EmergencyFeature]. The flow at trigger time:
 *
 *     long-press ─► UserFeature.TriggerEmergency
 *                       │
 *                       ▼
 *                  EmergencyFeature.TriggerAlert
 *                       │
 *                       ▼  news: BroadcastEmergency
 *                  EmergencyAlertEngine.persistAlertViaRest
 *                       │
 *                       ▼  POST /api/v1/incidents/sos
 *                  Backend persists + broadcasts
 *                       │
 *                       ▼  inbound: emergency.alert envelope
 *                  this interactor's gateway subscription
 *                       │
 *                       ▼
 *                  Engine.onIncomingAlert(...)
 *
 * No emergency envelope is ever sent OUTBOUND on the WebSocket. The gateway
 * is inbound-only for emergencies.
 */
class UserDashboardInteractor(
    private val userFeature: UserFeature = UserFeature(),
    private val emergencyFeature: EmergencyFeature = EmergencyFeature(),
    private val realtimeGateway: RealtimeGateway? = null,
    private val emergencyRepository: EmergencyRepository? = null,
    private val userRepository: UserRepository? = null,
    private val locationProvider: com.amanah.feature.core.location.LocationProvider? = null,
    private val appContext: android.content.Context? = null,
) : Interactor<UserDashboardView, UserDashboardRouter>() {

    private var engine: EmergencyAlertEngine? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private var emergencyAlertDispatched = false

    override fun onAttach() {
        Observable.wrap(userFeature).subscribe { state -> view?.render(state) }
            .autoDispose()

        Observable.wrap(userFeature.news).subscribe { news ->
            when (news) {
                UserNews.EmergencyTriggered ->
                    router?.onEmergencyTriggered()
                is UserNews.IncomingEmergency ->
                    router?.onIncomingEmergency(news.alertId, news.victimLat, news.victimLng)
                UserNews.Logout ->
                    router?.onLogout()
            }
        }.autoDispose()

        Observable.wrap(emergencyFeature).subscribe handler@{ emergencyState ->
                AmanahDebugDrawer.recordStateChange("EmergencyFeature", emergencyState)

                emergencyState.victimH3Cell?.let { cell ->
                    AmanahDebugDrawer.updateH3Context(
                        cellId        = cell,
                        resolution    = H3Resolution.DISTRICT,
                        searchedCells = setOfNotNull(emergencyState.victimH3CellBlock),
                    )
                }

                if (emergencyState.isActiveEmergency && !emergencyAlertDispatched) {
                    val lat  = emergencyState.victimLat ?: return@handler
                    val lng  = emergencyState.victimLng ?: return@handler
                    val cell = emergencyState.victimH3Cell ?: ""
                    emergencyAlertDispatched = true
                    userFeature.accept(
                        UserWish.IncomingEmergencyAlert(
                            alertId      = emergencyState.activeAlertId ?: "",
                            victimLat    = lat,
                            victimLng    = lng,
                            victimH3Cell = cell,
                        )
                    )

                    // Promote location tracking to EMERGENCY cadence and anchor
                    // the process via the foreground service so we survive any
                    // background-kill while the emergency is live.
                    locationProvider?.start(com.amanah.feature.core.location.TrackingProfile.EMERGENCY)
                    appContext?.let { ctx ->
                        com.amanah.feature.core.emergency.EmergencyForegroundService
                            .start(ctx, emergencyState.activeAlertId ?: "active")
                    }
                }

                if (emergencyState.phase == EmergencyState.Phase.IDLE && emergencyAlertDispatched) {
                    emergencyAlertDispatched = false
                    userFeature.accept(UserWish.CancelEmergency)

                    // Demote location cadence and release the foreground anchor.
                    locationProvider?.start(com.amanah.feature.core.location.TrackingProfile.ACTIVE)
                    appContext?.let { ctx ->
                        com.amanah.feature.core.emergency.EmergencyForegroundService.stop(ctx)
                    }
                }
            }.autoDispose()

        view?.events = { wish -> userFeature.accept(wish) }
    }

    override fun onDetach() {
        engine?.stop()
        engine = null
        view?.events = null
        userFeature.dispose()
        emergencyFeature.dispose()
        locationProvider?.stop()
        scope.cancel()
    }

    // ── Called by UserDashboardNode.onAttach() ────────────────────────────────

    fun initializeUser(user: AuthenticatedUser) {
        userFeature.accept(UserWish.Initialize(user))

        // Start collecting real location fixes for the duration of the session.
        // The provider is permission-aware — a no-op if location perms aren't
        // granted, in which case [snapshot()] returns null and the engine
        // skips outbound presence pings.
        locationProvider?.start(com.amanah.feature.core.location.TrackingProfile.ACTIVE)
        val userH3Cell = locationProvider?.currentH3Cell() ?: ""

        val repo = emergencyRepository
        if (repo != null) {
            engine = EmergencyAlertEngine(
                feature             = emergencyFeature,
                emergencyRepository = repo,
                currentUserId       = user.userId,
                currentUserH3Cell   = userH3Cell,
                onEtaAvailable      = { etaSeconds, distanceMeters ->
                    userFeature.accept(UserWish.EtaUpdated(etaSeconds, distanceMeters))
                },
                onResponderUpdate   = { responderId, lat, lng, etaSeconds, distanceMeters ->
                    userFeature.accept(
                        UserWish.UpdateResponderLocation(
                            ResponderInfo(
                                responderId    = responderId,
                                lat            = lat,
                                lng            = lng,
                                etaSeconds     = etaSeconds,
                                distanceMeters = distanceMeters,
                            )
                        )
                    )
                },
            ).also { it.start() }
        }

        // ── Subscribe to inbound realtime events ─────────────────────────────
        val gateway       = realtimeGateway ?: return
        val currentEngine = engine ?: return

        gateway.incoming
            .subscribe { event ->
                when (event) {
                    is RealtimeEvent.EmergencyAlert -> currentEngine.onIncomingAlert(
                        EmergencyAlertMessage(
                            alertId   = event.alertId,
                            victimId  = event.victimId,
                            lat       = event.lat,
                            lng       = event.lng,
                            h3Cell    = event.h3Cell,
                            status    = parseStatus(event.status),
                            timestamp = event.serverTsMs,
                            kRing     = event.kRing,
                        )
                    )
                    is RealtimeEvent.ResponderLocation -> currentEngine.onResponderLocationUpdate(
                        responderId  = event.responderId,
                        alertId      = event.alertId,
                        lat          = event.lat,
                        lng          = event.lng,
                        etaSeconds   = event.etaSeconds,
                        timestampMs  = event.serverTsMs,
                    )
                    else -> Unit  // other types handled by sibling interactors
                }
            }
            .autoDispose()

        // ── Eagerly hydrate the dashboard from real backend data ─────────────
        userRepository?.let { repo -> loadInitialFromBackend(repo) }
    }

    /**
     * Pull alert history + (eventually) nearby members from the backend.
     *
     * Nearby members require the `/api/v1/users/nearby` endpoint which is
     * tracked separately — until that lands the dashboard shows the alert
     * history but not the nearby grid.
     */
    private fun loadInitialFromBackend(repo: UserRepository) {
        // 1) Alert history
        scope.launch {
            when (val outcome = repo.listMyActiveIncidents()) {
                is Outcome.Success -> {
                    val alerts = outcome.value.map { incident ->
                        AlertSummary(
                            alertId      = incident.id,
                            triggeredAt  = System.currentTimeMillis(),
                            statusLabel  = incident.status,
                            wasResponder = false,
                        )
                    }
                    userFeature.accept(UserWish.AlertsLoaded(alerts))
                }
                else -> Unit  // interceptor handles AuthFailed
            }
        }

        // 2) Nearby grid — only useful if we have a fix
        scope.launch {
            val h3 = locationProvider?.currentH3Cell() ?: run {
                userFeature.accept(UserWish.NearbyLoaded(emptyList()))
                return@launch
            }
            // First push our own presence so we appear in others' nearby lists.
            repo.pingPresence(h3, locationProvider?.currentH3Cell(
                com.amanah.lib.location.H3Resolution.BLOCK))

            // Compute k-ring locally, ask backend for matches.
            val fix = locationProvider?.snapshot() ?: return@launch
            val kRingCells = runCatching {
                com.amanah.lib.location.H3LocationIndex.nearbyAddresses(
                    lat        = fix.lat,
                    lng        = fix.lng,
                    resolution = com.amanah.lib.location.H3Resolution.DISTRICT,
                    kRings     = com.amanah.lib.location.H3Resolution.EMERGENCY_K_RING,
                ).toList()
            }.getOrDefault(listOf(h3))

            when (val outcome = repo.listNearby(cells = kRingCells)) {
                is Outcome.Success -> {
                    val nearby = outcome.value.items.map { dto ->
                        com.amanah.feature.user.mvi.NearbyUser(
                            userId      = dto.userId,
                            displayName = dto.displayName,
                            lat         = 0.0,   // server returns H3 only; we never receive raw GPS
                            lng         = 0.0,
                            h3Cell      = dto.h3CellDistrict,
                            isExact     = false,
                        )
                    }
                    userFeature.accept(UserWish.NearbyLoaded(nearby))
                }
                else -> userFeature.accept(UserWish.NearbyLoaded(emptyList()))
            }
        }
    }

    // ── External injection (FCM push / RootNode path) ─────────────────────────

    /** Called by [RootNode] when a push notification carries an incoming alert. */
    fun onIncomingAlert(alertId: String, victimLat: Double, victimLng: Double) {
        userFeature.accept(
            UserWish.IncomingEmergencyAlert(
                alertId      = alertId,
                victimLat    = victimLat,
                victimLng    = victimLng,
                victimH3Cell = "",
            )
        )
    }

    private fun parseStatus(name: String): EmergencyAlertStatus =
        runCatching { EmergencyAlertStatus.valueOf(name) }
            .getOrDefault(EmergencyAlertStatus.ACTIVE)
}
