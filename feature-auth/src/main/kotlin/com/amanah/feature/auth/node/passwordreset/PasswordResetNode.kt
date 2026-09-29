package com.amanah.feature.auth.node.passwordreset

import com.amanah.lib.nodes.Interactor
import com.amanah.lib.nodes.Node
import com.amanah.lib.nodes.NodeContext
import com.amanah.lib.nodes.Router

class PasswordResetInteractor : Interactor<PasswordResetView, PasswordResetRouter>() {
    override fun onAttach() {
        view?.render(PasswordResetState())
        view?.events = { event ->
            when (event) {
                is PasswordResetEvent.ContactChanged ->
                    view?.render(PasswordResetState(contactValue = event.value))
                PasswordResetEvent.Submit -> {
                    view?.render(PasswordResetState(isSubmitted = true))
                    // TODO: wire to AdminNotificationRepository
                }
                PasswordResetEvent.Back -> router?.navigateBack()
            }
        }
    }
    override fun onDetach() { view?.events = null }
}

class PasswordResetRouter(
    interactor: PasswordResetInteractor,
    private val onBack: () -> Unit,
) : Router<PasswordResetInteractor>(interactor) {
    fun navigateBack() = onBack()
}

class PasswordResetNode(
    nodeContext: NodeContext,
    onBack: () -> Unit,
) : Node<PasswordResetView, PasswordResetInteractor, PasswordResetRouter>(
    nodeContext   = nodeContext,
    viewFactory   = { PasswordResetView() },
    interactor    = PasswordResetInteractor(),
    routerFactory = { interactor -> PasswordResetRouter(interactor, onBack) },
)
