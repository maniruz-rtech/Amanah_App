package com.amanah.feature.core.ui

import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.PaddingValues
import com.badoo.reaktive.observable.subscribe
import kotlinx.coroutines.launch

/**
 * Wraps Material 3 [Scaffold] with:
 *   - Amanah top bar slot (defaults to no bar)
 *   - Amanah bottom bar slot
 *   - A SnackbarHost that subscribes to the optional [snackbarBus]; if no bus
 *     is provided the host still works for local `Scaffold`-style snackbars.
 *
 * The bus subscription disposes automatically when the scaffold leaves the
 * composition.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AmanahScaffold(
    modifier: Modifier = Modifier,
    topBar: @Composable () -> Unit = {},
    bottomBar: @Composable () -> Unit = {},
    floatingActionButton: @Composable () -> Unit = {},
    snackbarBus: GlobalSnackbarBus? = null,
    containerColor: androidx.compose.ui.graphics.Color = MaterialTheme.colorScheme.background,
    content: @Composable (PaddingValues) -> Unit,
) {
    val snackbarHostState = remember { SnackbarHostState() }
    val scope             = rememberCoroutineScope()

    if (snackbarBus != null) {
        DisposableEffect(snackbarBus) {
            val disposable = snackbarBus.stream.subscribe { msg ->
                scope.launch {
                    val result = snackbarHostState.showSnackbar(
                        message     = msg.text,
                        actionLabel = msg.actionLabel,
                        duration    = msg.duration,
                    )
                    if (result == SnackbarResult.ActionPerformed) {
                        msg.onAction?.invoke()
                    }
                }
            }
            onDispose { disposable.dispose() }
        }
    }

    Scaffold(
        modifier             = modifier,
        topBar               = topBar,
        bottomBar            = bottomBar,
        floatingActionButton = floatingActionButton,
        snackbarHost         = { SnackbarHost(snackbarHostState) },
        containerColor       = containerColor,
        content              = content,
    )
}
