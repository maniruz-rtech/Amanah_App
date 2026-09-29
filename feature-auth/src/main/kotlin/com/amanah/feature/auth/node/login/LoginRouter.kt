package com.amanah.feature.auth.node.login

import com.amanah.feature.auth.model.AuthenticatedUser
import com.amanah.lib.nodes.Router

/**
 * "Flow" layer of LoginNode.
 *
 * Role-based routing: post-auth, the router inspects the user's role and
 * dispatches to either the Admin or User dashboard. This is the single
 * authoritative routing decision point — no other node performs role checks.
 */
class LoginRouter(
    interactor: LoginInteractor,
    private val onAdminAuthenticated: (AuthenticatedUser) -> Unit,
    private val onUserAuthenticated: (AuthenticatedUser) -> Unit,
    private val onPasswordResetRequested: () -> Unit,
) : Router<LoginInteractor>(interactor) {

    fun navigateToAdmin(user: AuthenticatedUser) = onAdminAuthenticated(user)

    fun navigateToUser(user: AuthenticatedUser) = onUserAuthenticated(user)

    fun navigateToPasswordReset() = onPasswordResetRequested()
}
