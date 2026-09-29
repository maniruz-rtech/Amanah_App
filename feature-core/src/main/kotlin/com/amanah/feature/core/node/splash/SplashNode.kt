package com.amanah.feature.core.node.splash

import com.amanah.lib.nodes.Node
import com.amanah.lib.nodes.NodeContext

/**
 * Entry point into the Splash screen sub-tree.
 *
 * Attached by [com.amanah.app.node.RootNode] on app start and detached once
 * [SplashEvent.AnimationComplete] fires; the router then hands control to the
 * Login flow.
 */
class SplashNode(
    nodeContext: NodeContext,
    onNavigateToDashboard: () -> Unit,
) : Node<SplashView, SplashInteractor, SplashRouter>(
    nodeContext   = nodeContext,
    viewFactory   = { SplashView() },
    interactor    = SplashInteractor(),
    routerFactory = { interactor ->
        SplashRouter(interactor, onNavigateToDashboard)
    },
)
