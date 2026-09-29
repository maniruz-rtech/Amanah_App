package com.amanah.feature.core.node.splash

import com.amanah.lib.nodes.Interactor
import com.badoo.reaktive.observable.subscribe

class SplashInteractor : Interactor<SplashView, SplashRouter>() {

    override fun onAttach() {
        // Wire view events → routing decisions
        view?.events = { event ->
            when (event) {
                SplashEvent.AnimationComplete -> router?.onSplashComplete()
            }
        }

        // Trigger render with initial state so the Compose tree has a value
        view?.render(SplashState())
    }

    override fun onDetach() {
        view?.events = null
    }
}
