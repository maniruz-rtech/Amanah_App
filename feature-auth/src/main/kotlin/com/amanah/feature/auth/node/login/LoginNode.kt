package com.amanah.feature.auth.node.login

import com.amanah.feature.auth.model.AuthenticatedUser
import com.amanah.feature.auth.mvi.LoginFeature
import com.amanah.feature.auth.repository.AuthRepository
import com.amanah.lib.nodes.Node
import com.amanah.lib.nodes.NodeContext

/**
 * Owns the login sub-tree. Attached by [RootNode] immediately after the Splash
 * animation; detached once the user successfully authenticates.
 *
 * The router performs the role check and calls the correct callback — this
 * node never needs to know whether its parent is routing to Admin or User.
 *
 * Pass an [authRepository] from the app graph to wire authentication to the
 * backend; if omitted the feature falls back to its stub authenticator (useful
 * for screen previews and tests).
 */
class LoginNode(
    nodeContext: NodeContext,
    onAdminAuthenticated: (AuthenticatedUser) -> Unit,
    onUserAuthenticated: (AuthenticatedUser) -> Unit,
    onPasswordResetRequested: () -> Unit,
    authRepository: AuthRepository? = null,
) : Node<LoginView, LoginInteractor, LoginRouter>(
    nodeContext   = nodeContext,
    viewFactory   = { LoginView() },
    interactor    = LoginInteractor(
        feature = if (authRepository != null) {
            LoginFeature(authenticate = { email, pwd -> authRepository.login(email, pwd) })
        } else {
            LoginFeature()
        }
    ),
    routerFactory = { interactor ->
        LoginRouter(interactor, onAdminAuthenticated, onUserAuthenticated, onPasswordResetRequested)
    },
)
