package com.amanah.feature.auth.node.onboarding

import com.amanah.lib.nodes.Interactor

/**
 * Lightweight interactor — onboarding has no remote state, just a local
 * page-index that advances on Next or skips to the end.
 *
 * Routing decision ("done — go to login") lives entirely in [OnboardingRouter].
 */
class OnboardingInteractor : Interactor<OnboardingView, OnboardingRouter>() {

    private var pageIndex = 0

    override fun onAttach() {
        view?.render(OnboardingState(pageIndex = pageIndex))
        view?.events = { event ->
            when (event) {
                OnboardingEvent.Next -> {
                    if (pageIndex == OnboardingState.PAGES_LAST_INDEX) {
                        router?.onCompleted()
                    } else {
                        pageIndex += 1
                        view?.render(OnboardingState(pageIndex = pageIndex))
                    }
                }
                OnboardingEvent.Skip -> router?.onCompleted()
            }
        }
    }

    override fun onDetach() {
        view?.events = null
    }
}
