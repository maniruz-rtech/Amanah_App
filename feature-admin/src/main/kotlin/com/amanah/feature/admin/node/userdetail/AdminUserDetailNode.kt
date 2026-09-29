package com.amanah.feature.admin.node.userdetail

import com.amanah.feature.admin.repository.AdminRepository
import com.amanah.lib.nodes.Node
import com.amanah.lib.nodes.NodeContext

class AdminUserDetailNode(
    nodeContext: NodeContext,
    val userId: String,
    onBack: () -> Unit,
    onUserUpdated: (userId: String) -> Unit,
    repository: AdminRepository? = null,
) : Node<AdminUserDetailView, AdminUserDetailInteractor, AdminUserDetailRouter>(
    nodeContext   = nodeContext,
    viewFactory   = { AdminUserDetailView() },
    interactor    = AdminUserDetailInteractor(userId = userId, repository = repository),
    routerFactory = { interactor -> AdminUserDetailRouter(interactor, onBack, onUserUpdated) },
)
