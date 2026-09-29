package com.amanah.feature.core.ui

import androidx.compose.material3.SnackbarDuration
import com.badoo.reaktive.observable.Observable
import com.badoo.reaktive.subject.publish.PublishSubject

/**
 * Process-wide snackbar bus.
 *
 * Any feature can `post(...)` a message; the active [AmanahScaffold] subscribes
 * to [stream] and presents the snackbar. This replaces the prop-drilled
 * `onShowSnackbar` / `onShowToast` lambdas scattered through the Node tree.
 *
 * Implemented as a [PublishSubject] (Reaktive), so:
 *   - subscribers only receive messages emitted *after* they subscribe;
 *   - no replay of stale messages on screen change;
 *   - safe to publish from any thread (Reaktive serialises).
 *
 * Inject this singleton via Dagger (see [AppComponent]).
 */
class GlobalSnackbarBus {

    private val subject = PublishSubject<SnackbarMessage>()

    val stream: Observable<SnackbarMessage> = subject

    fun post(text: String, severity: SnackbarSeverity = SnackbarSeverity.INFO) {
        subject.onNext(SnackbarMessage(text = text, severity = severity))
    }

    fun postAction(
        text: String,
        actionLabel: String,
        severity: SnackbarSeverity = SnackbarSeverity.INFO,
        onAction: () -> Unit,
    ) {
        subject.onNext(
            SnackbarMessage(
                text        = text,
                severity    = severity,
                actionLabel = actionLabel,
                onAction    = onAction,
            )
        )
    }
}

enum class SnackbarSeverity { INFO, SUCCESS, WARNING, ERROR }

data class SnackbarMessage(
    val text: String,
    val severity: SnackbarSeverity = SnackbarSeverity.INFO,
    val actionLabel: String? = null,
    val onAction: (() -> Unit)? = null,
    val duration: SnackbarDuration =
        if (severity == SnackbarSeverity.ERROR) SnackbarDuration.Long else SnackbarDuration.Short,
)
