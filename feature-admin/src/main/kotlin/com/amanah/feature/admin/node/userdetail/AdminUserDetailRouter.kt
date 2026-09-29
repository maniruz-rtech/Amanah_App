package com.amanah.feature.admin.node.userdetail

import com.amanah.lib.nodes.Router

class AdminUserDetailRouter(
    interactor: AdminUserDetailInteractor,
    private val onBackCallback: () -> Unit,
    private val onUserUpdatedCallback: (userId: String) -> Unit,
) : Router<AdminUserDetailInteractor>(interactor) {

    fun onBack() = onBackCallback()
    fun onUserUpdated(userId: String) = onUserUpdatedCallback(userId)
}
