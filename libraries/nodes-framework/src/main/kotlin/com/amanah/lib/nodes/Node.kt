package com.amanah.lib.nodes

import android.content.Context

/**
 * Root abstraction of the Node tree.
 *
 * A [Node] composes exactly three collaborators:
 *   - [ViewType]       — the Compose-based presentation ("View")
 *   - [InteractorType] — business logic and state owner ("Context")
 *   - [RouterType]     — child attachment / navigation ("Flow")
 *
 * Nodes are fully decoupled: they communicate only through typed interfaces,
 * never through direct references to sibling or parent nodes.
 *
 * Typical subclass pattern:
 * ```
 * class LoginNode(nodeContext: NodeContext) : Node<LoginView, LoginInteractor, LoginRouter>(
 *     nodeContext    = nodeContext,
 *     viewFactory    = { ctx -> LoginComposeView(ctx) },
 *     interactor     = LoginInteractor(),
 *     routerFactory  = { interactor -> LoginRouter(interactor) },
 * )
 * ```
 */
@Suppress("FINITE_BOUNDS_VIOLATION")
abstract class Node<
    ViewType : NodeView<*, *>,
    InteractorType : Interactor<ViewType, RouterType>,
    RouterType : Router<InteractorType>,
>(
    val nodeContext: NodeContext,
    private val viewFactory: (Context) -> ViewType,
    val interactor: InteractorType,
    private val routerFactory: (InteractorType) -> RouterType,
) {
    private var _view: ViewType? = null
    private var _router: RouterType? = null

    val view: ViewType
        get() = _view ?: error("View accessed before onAttach()")

    val router: RouterType
        get() = _router ?: error("Router accessed before onAttach()")

    fun performAttach() {
        val v = viewFactory(nodeContext.androidContext).also { _view = it }
        val r = routerFactory(interactor).also { _router = it }
        interactor.attach(v, r)
        r.onAttach()
        onAttach()
    }

    fun performDetach() {
        onDetach()
        _router?.onDetach()
        interactor.detach()
        _view = null
        _router = null
    }

    protected open fun onAttach() {}
    protected open fun onDetach() {}
}
