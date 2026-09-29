package com.amanah.feature.core.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

/**
 * Centered indeterminate progress with an optional message.
 *
 * Drop into any `Box(Modifier.fillMaxSize())` slot. Compose only —
 * carries no behaviour, doesn't subscribe to anything.
 */
@Composable
fun AmanahLoadingState(
    message: String? = null,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier              = modifier.fillMaxSize(),
        horizontalAlignment   = Alignment.CenterHorizontally,
        verticalArrangement   = Arrangement.Center,
    ) {
        CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
        if (message != null) {
            Spacer(Modifier.height(AmanahSpacing.md))
            Text(
                text       = message,
                style      = MaterialTheme.typography.bodyMedium,
                color      = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign  = TextAlign.Center,
                modifier   = Modifier.padding(horizontal = AmanahSpacing.lg),
            )
        }
    }
}

/**
 * Empty-state slot.
 *
 * Use when a list/grid has 0 rows but no error occurred. Renders an icon, a
 * title, an optional body, and an optional primary action button.
 */
@Composable
fun AmanahEmptyState(
    title: String,
    icon: ImageVector,
    body: String? = null,
    actionText: String? = null,
    onAction: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier              = modifier.fillMaxSize().padding(AmanahSpacing.lg),
        horizontalAlignment   = Alignment.CenterHorizontally,
        verticalArrangement   = Arrangement.Center,
    ) {
        Icon(
            imageVector        = icon,
            contentDescription = null,
            tint               = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier           = Modifier.size(56.dp),
        )
        Spacer(Modifier.height(AmanahSpacing.md))
        Text(
            text       = title,
            style      = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
            color      = MaterialTheme.colorScheme.onSurface,
            textAlign  = TextAlign.Center,
        )
        if (body != null) {
            Spacer(Modifier.height(AmanahSpacing.sm))
            Text(
                text       = body,
                style      = MaterialTheme.typography.bodyMedium,
                color      = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign  = TextAlign.Center,
            )
        }
        if (actionText != null && onAction != null) {
            Spacer(Modifier.height(AmanahSpacing.lg))
            AmanahPrimaryButton(text = actionText, onClick = onAction)
        }
    }
}

/**
 * Generic error state. Always offers a Retry button if [onRetry] is provided;
 * otherwise renders just the message.
 */
@Composable
fun AmanahErrorState(
    message: String,
    modifier: Modifier = Modifier,
    title: String = "Something went wrong",
    onRetry: (() -> Unit)? = null,
) {
    Column(
        modifier              = modifier.fillMaxSize().padding(AmanahSpacing.lg),
        horizontalAlignment   = Alignment.CenterHorizontally,
        verticalArrangement   = Arrangement.Center,
    ) {
        Icon(
            imageVector        = Icons.Default.ErrorOutline,
            contentDescription = null,
            tint               = MaterialTheme.colorScheme.error,
            modifier           = Modifier.size(56.dp),
        )
        Spacer(Modifier.height(AmanahSpacing.md))
        Text(
            text       = title,
            style      = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
            color      = MaterialTheme.colorScheme.onSurface,
            textAlign  = TextAlign.Center,
        )
        Spacer(Modifier.height(AmanahSpacing.sm))
        Text(
            text       = message,
            style      = MaterialTheme.typography.bodyMedium,
            color      = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign  = TextAlign.Center,
        )
        if (onRetry != null) {
            Spacer(Modifier.height(AmanahSpacing.lg))
            AmanahSecondaryButton(text = "Retry", onClick = onRetry, leadingIcon = Icons.Default.Refresh)
        }
    }
}

