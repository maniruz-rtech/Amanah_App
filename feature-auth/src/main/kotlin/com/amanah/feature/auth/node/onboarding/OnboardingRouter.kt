package com.amanah.feature.auth.node.onboarding

import com.amanah.lib.nodes.Router

class OnboardingRouter(
    interactor: OnboardingInteractor,
    private val onCompletedCallback: () -> Unit,
) : Router<OnboardingInteractor>(interactor) {

    fun onCompleted() = onCompletedCallback()
}
