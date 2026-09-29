package com.amanah.feature.auth.node.onboarding

import com.amanah.lib.nodes.Node
import com.amanah.lib.nodes.NodeContext

/**
 * 3-page onboarding flow attached on first launch (when no auth token is
 * persisted). Calls back via [onCompleted] when the user reaches the last
 * page and taps "Get Started" or taps "Skip" at any point.
 */
class OnboardingNode(
    nodeContext: NodeContext,
    onCompleted: () -> Unit,
) : Node<OnboardingView, OnboardingInteractor, OnboardingRouter>(
    nodeContext   = nodeContext,
    viewFactory   = { OnboardingView() },
    interactor    = OnboardingInteractor(),
    routerFactory = { interactor -> OnboardingRouter(interactor, onCompleted) },
)
