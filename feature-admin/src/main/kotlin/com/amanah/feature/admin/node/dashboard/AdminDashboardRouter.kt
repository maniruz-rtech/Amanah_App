package com.amanah.feature.admin.node.dashboard

import com.amanah.lib.nodes.Router

class AdminDashboardRouter(
    interactor: AdminDashboardInteractor,
    private val onEditUser: (userId: String) -> Unit,
    private val onShowToast: (message: String) -> Unit,
) : Router<AdminDashboardInteractor>(interactor) {

    fun navigateToEditUser(userId: String) = onEditUser(userId)
    fun showToast(message: String) = onShowToast(message)
}
