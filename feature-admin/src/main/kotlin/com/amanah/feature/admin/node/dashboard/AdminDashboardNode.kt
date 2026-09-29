package com.amanah.feature.admin.node.dashboard

import com.amanah.feature.admin.repository.AdminRepository
import com.amanah.feature.auth.model.AuthenticatedUser
import com.amanah.lib.nodes.Node
import com.amanah.lib.nodes.NodeContext

/**
 * Admin Command Center node.
 *
 * Attached by [RootNode] after [LoginRouter] confirms [UserRole.ADMIN].
 * Owns the full admin lifecycle: user management, alert history, live alerts.
 *
 * Pass [repository] from the app graph to wire to real backend data; if null
 * the screen renders an empty/loading state.
 */
class AdminDashboardNode(
    nodeContext: NodeContext,
    @Suppress("UNUSED_PARAMETER") admin: AuthenticatedUser,
    onEditUser: (userId: String) -> Unit,
    onShowToast: (message: String) -> Unit,
    repository: AdminRepository? = null,
) : Node<AdminDashboardView, AdminDashboardInteractor, AdminDashboardRouter>(
    nodeContext   = nodeContext,
    viewFactory   = { AdminDashboardView() },
    interactor    = AdminDashboardInteractor(repository = repository),
    routerFactory = { interactor ->
        AdminDashboardRouter(interactor, onEditUser, onShowToast)
    },
)
