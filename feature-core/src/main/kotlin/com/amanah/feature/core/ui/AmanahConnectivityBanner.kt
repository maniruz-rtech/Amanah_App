package com.amanah.feature.core.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.WifiOff
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier

/**
 * Inset banner shown when the WebSocket / network connectivity drops.
 *
 * Place at the top of the body inside [AmanahScaffold] *below* the top app bar
 * but above the screen content, so it doesn't shift the layout when shown/hidden.
 */
@Composable
fun AmanahConnectivityBanner(
    isConnected: Boolean,
    modifier: Modifier = Modifier,
    offlineLabel: String = "You're offline — alerts may be delayed.",
) {
    AnimatedVisibility(
        visible = !isConnected,
        enter   = fadeIn(AmanahMotion.fastTween()),
        exit    = fadeOut(AmanahMotion.fastTween()),
        modifier = modifier,
    ) {
        Row(
            modifier              = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.errorContainer)
                .padding(horizontal = AmanahSpacing.md, vertical = AmanahSpacing.sm),
            verticalAlignment     = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(AmanahSpacing.sm),
        ) {
            Icon(
                imageVector        = Icons.Default.WifiOff,
                contentDescription = null,
                tint               = MaterialTheme.colorScheme.onErrorContainer,
            )
            Text(
                text  = offlineLabel,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
        }
    }
}
