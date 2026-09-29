package com.amanah.lib.nodes

/**
 * "Flow" layer of the Node — owns navigation decisions.
 *
 * The router is the only component allowed to attach or detach child [Node]s.
 * No business logic lives here; it only reacts to routing commands emitted by
 * the [Interactor] via sealed routing action types.
 */
@Suppress("FINITE_BOUNDS_VIOLATION")
abstract class Router<InteractorType : Interactor<*, *>>(
    protected val interactor: InteractorType,
) {
    private val attachedChildren = ArrayDeque<Node<*, *, *>>()

    open fun onAttach() {}

    open fun onDetach() {
        detachAllChildren()
    }

    protected fun attachChild(node: Node<*, *, *>) {
        attachedChildren.addLast(node)
        node.performAttach()
    }

    protected fun detachChild(node: Node<*, *, *>) {
        node.performDetach()
        attachedChildren.remove(node)
    }

    private fun detachAllChildren() {
        attachedChildren.toList().forEach { it.performDetach() }
        attachedChildren.clear()
    }
}
