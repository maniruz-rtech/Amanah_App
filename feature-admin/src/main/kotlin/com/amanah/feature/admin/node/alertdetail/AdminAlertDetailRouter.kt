package com.amanah.feature.admin.node.alertdetail

import com.amanah.lib.nodes.Router

class AdminAlertDetailRouter(
    interactor: AdminAlertDetailInteractor,
    private val onBackCallback: () -> Unit,
    private val onResolvedCallback: (alertId: String) -> Unit,
) : Router<AdminAlertDetailInteractor>(interactor) {

    fun onBack() = onBackCallback()
    fun onResolved(alertId: String) = onResolvedCallback(alertId)
}
