package com.amanah.feature.user.node.incidentdetail

import com.amanah.lib.nodes.Router

class IncidentDetailRouter(
    interactor: IncidentDetailInteractor,
    private val onBackCallback: () -> Unit,
) : Router<IncidentDetailInteractor>(interactor) {

    fun onBack() = onBackCallback()
}
