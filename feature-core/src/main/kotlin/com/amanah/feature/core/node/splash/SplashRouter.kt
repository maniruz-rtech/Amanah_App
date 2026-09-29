package com.amanah.feature.core.node.splash

import com.amanah.lib.nodes.Router

class SplashRouter(
    interactor: SplashInteractor,
    private val onNavigateToDashboard: () -> Unit,
) : Router<SplashInteractor>(interactor) {

    fun onSplashComplete() {
        onNavigateToDashboard()
    }
}
