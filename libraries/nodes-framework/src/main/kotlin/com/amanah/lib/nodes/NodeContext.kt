package com.amanah.lib.nodes

import android.content.Context
import com.badoo.mobile.util.WeakHandler

/**
 * Per-node dependency container. Every [Node] receives its own [NodeContext],
 * ensuring that Android [Context] access and handler lifecycle are scoped to
 * exactly one node — no leaks propagate up the tree.
 */
data class NodeContext(
    val androidContext: Context,
    val weakHandler: WeakHandler = WeakHandler(),
    val parent: NodeContext? = null,
) {
    fun child(): NodeContext = NodeContext(
        androidContext = androidContext,
        parent = this,
    )
}
