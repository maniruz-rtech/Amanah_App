package com.amanah.feature.user.node.incidentdetail

import com.amanah.feature.user.repository.UserRepository
import com.amanah.lib.nodes.Node
import com.amanah.lib.nodes.NodeContext

/**
 * User-side drill-down for a single incident.
 *
 * Reached from:
 *   - User dashboard "Alerts" tab card tap.
 *   - The active-emergency overlay (drill into history while live).
 */
class IncidentDetailNode(
    nodeContext: NodeContext,
    val alertId: String,
    onBack: () -> Unit,
    userRepository: UserRepository? = null,
) : Node<IncidentDetailView, IncidentDetailInteractor, IncidentDetailRouter>(
    nodeContext   = nodeContext,
    viewFactory   = { IncidentDetailView() },
    interactor    = IncidentDetailInteractor(alertId = alertId, userRepository = userRepository),
    routerFactory = { interactor -> IncidentDetailRouter(interactor, onBack) },
)
