package com.amanah.feature.admin.node.alertdetail

import com.amanah.feature.admin.repository.AdminRepository
import com.amanah.lib.nodes.Node
import com.amanah.lib.nodes.NodeContext

class AdminAlertDetailNode(
    nodeContext: NodeContext,
    val alertId: String,
    onBack: () -> Unit,
    onResolved: (alertId: String) -> Unit,
    repository: AdminRepository? = null,
) : Node<AdminAlertDetailView, AdminAlertDetailInteractor, AdminAlertDetailRouter>(
    nodeContext   = nodeContext,
    viewFactory   = { AdminAlertDetailView() },
    interactor    = AdminAlertDetailInteractor(alertId = alertId, repository = repository),
    routerFactory = { interactor -> AdminAlertDetailRouter(interactor, onBack, onResolved) },
)
