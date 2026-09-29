package com.amanah.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.core.view.WindowCompat
import com.amanah.app.node.RootNode
import com.amanah.lib.nodes.NodeContext

/**
 * Single-Activity host — intentionally minimal.
 *
 * All navigation, state, and business logic live in the Node tree. The Activity
 * only bridges Android lifecycle events to the root [RootNode] and hosts the
 * Compose content slot.
 */
class MainActivity : ComponentActivity() {

    private lateinit var rootNode: RootNode

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        enableEdgeToEdge()
        WindowCompat.setDecorFitsSystemWindows(window, false)

        val graph = (application as AmanahApplication).graph

        rootNode = RootNode(
            nodeContext = NodeContext(androidContext = applicationContext),
            graph       = graph,
        ).also { it.onAttach() }

        setContent { rootNode.Content() }
    }

    override fun onDestroy() {
        super.onDestroy()
        rootNode.onDetach()
    }
}
