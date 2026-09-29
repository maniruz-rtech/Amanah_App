package com.amanah.feature.user.node.dashboard

import com.amanah.feature.auth.model.AuthenticatedUser
import com.amanah.feature.core.realtime.RealtimeGateway
import com.amanah.feature.emergency.repository.EmergencyRepository
import com.amanah.feature.user.repository.UserRepository
import com.amanah.lib.nodes.Node
import com.amanah.lib.nodes.NodeContext

/**
 * User safety panel.
 *
 * Repository wiring:
 *   - [emergencyRepository] is the canonical persistence path for the SOS
 *     long-press. Required for SOS to leave a forensic trace.
 *   - [userRepository] hydrates the dashboard tabs from the backend.
 *   - [realtimeGateway] is the inbound channel for fanout events; never used
 *     to trigger an SOS.
 *
 * Each can be null for preview / test mode.
 */
class UserDashboardNode(
    nodeContext: NodeContext,
    val authenticatedUser: AuthenticatedUser,
    onEmergencyTriggered: () -> Unit,
    onIncomingEmergency: (alertId: String, lat: Double, lng: Double) -> Unit,
    onLogout: () -> Unit,
    realtimeGateway: RealtimeGateway? = null,
    emergencyRepository: EmergencyRepository? = null,
    userRepository: UserRepository? = null,
    locationProvider: com.amanah.feature.core.location.LocationProvider? = null,
) : Node<UserDashboardView, UserDashboardInteractor, UserDashboardRouter>(
    nodeContext   = nodeContext,
    viewFactory   = { UserDashboardView(nodeContext.weakHandler) },
    interactor    = UserDashboardInteractor(
        realtimeGateway     = realtimeGateway,
        emergencyRepository = emergencyRepository,
        userRepository      = userRepository,
        locationProvider    = locationProvider,
        appContext          = nodeContext.androidContext,
    ),
    routerFactory = { interactor ->
        UserDashboardRouter(interactor, onEmergencyTriggered, onIncomingEmergency, onLogout)
    },
) {
    override fun onAttach() {
        interactor.initializeUser(authenticatedUser)
    }
}
