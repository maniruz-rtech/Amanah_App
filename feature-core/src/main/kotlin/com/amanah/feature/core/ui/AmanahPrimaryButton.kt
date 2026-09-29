package com.amanah.feature.core.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp

/**
 * The single primary CTA across the app.
 *
 * - Renders a centered title.
 * - When [loading], swaps the title for a small spinner and disables clicks.
 * - When [leadingIcon] is non-null, prepends it with standard spacing.
 *
 * Always full-width and [AmanahTouch.BUTTON_HEIGHT] tall.
 */
@Composable
fun AmanahPrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    leadingIcon: ImageVector? = null,
) {
    Button(
        onClick  = onClick,
        enabled  = enabled && !loading,
        modifier = modifier
            .fillMaxWidth()
            .height(AmanahTouch.BUTTON_HEIGHT),
        colors   = ButtonDefaults.buttonColors(),
    ) {
        if (loading) {
            CircularProgressIndicator(
                modifier    = Modifier.size(22.dp),
                strokeWidth = 2.dp,
                color       = MaterialTheme.colorScheme.onPrimary,
            )
        } else {
            Row(
                verticalAlignment     = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center,
            ) {
                if (leadingIcon != null) {
                    Icon(leadingIcon, contentDescription = null)
                    Spacer(Modifier.width(AmanahSpacing.sm))
                }
                Text(text, style = MaterialTheme.typography.titleMedium)
            }
        }
    }
}

/** Outlined / secondary variant of [AmanahPrimaryButton]. */
@Composable
fun AmanahSecondaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    leadingIcon: ImageVector? = null,
) {
    OutlinedButton(
        onClick  = onClick,
        enabled  = enabled,
        modifier = modifier
            .fillMaxWidth()
            .height(AmanahTouch.BUTTON_HEIGHT),
    ) {
        Row(
            verticalAlignment     = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center,
        ) {
            if (leadingIcon != null) {
                Icon(leadingIcon, contentDescription = null)
                Spacer(Modifier.width(AmanahSpacing.sm))
            }
            Text(text, style = MaterialTheme.typography.titleMedium)
        }
    }
}

/**
 * Red, error-coloured primary button. Use for destructive or irreversible
 * actions (Cancel Emergency, Sign Out, Force Resolve, Suspend User, etc.).
 */
@Composable
fun AmanahDestructiveButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    leadingIcon: ImageVector? = null,
) {
    Button(
        onClick  = onClick,
        enabled  = enabled && !loading,
        modifier = modifier
            .fillMaxWidth()
            .height(AmanahTouch.BUTTON_HEIGHT),
        colors   = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.error,
            contentColor   = MaterialTheme.colorScheme.onError,
        ),
    ) {
        if (loading) {
            CircularProgressIndicator(
                modifier    = Modifier.size(22.dp),
                strokeWidth = 2.dp,
                color       = MaterialTheme.colorScheme.onError,
            )
        } else {
            Row(
                verticalAlignment     = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center,
            ) {
                if (leadingIcon != null) {
                    Icon(leadingIcon, contentDescription = null)
                    Spacer(Modifier.width(AmanahSpacing.sm))
                }
                Text(text, style = MaterialTheme.typography.titleMedium)
            }
        }
    }
}
