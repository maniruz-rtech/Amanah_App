package com.amanah.feature.user.node.dashboard

import com.amanah.lib.nodes.Router

class UserDashboardRouter(
    interactor: UserDashboardInteractor,
    private val onEmergencyTriggered: () -> Unit,
    private val onIncomingEmergency: (alertId: String, lat: Double, lng: Double) -> Unit,
    private val onLogout: () -> Unit,
) : Router<UserDashboardInteractor>(interactor) {

    fun onEmergencyTriggered() = onEmergencyTriggered.invoke()

    fun onIncomingEmergency(alertId: String, victimLat: Double, victimLng: Double) =
        onIncomingEmergency.invoke(alertId, victimLat, victimLng)

    fun onLogout() = onLogout.invoke()
}
