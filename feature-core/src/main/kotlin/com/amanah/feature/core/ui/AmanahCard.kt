package com.amanah.feature.core.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardColors
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp

/**
 * Standard Amanah card.
 *
 * - Default elevation [AmanahElevation.md].
 * - Default content padding [AmanahSpacing.md].
 * - Optional [onClick] turns the card into a clickable surface.
 * - Optional [containerColor] overrides the theme surface (e.g. errorContainer
 *   for active-emergency cards).
 */
@Composable
fun AmanahCard(
    modifier: Modifier = Modifier,
    elevation: Dp = AmanahElevation.md,
    contentPadding: Dp = AmanahSpacing.md,
    containerColor: Color = MaterialTheme.colorScheme.surface,
    onClick: (() -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    val rootModifier = if (onClick != null) modifier.clickable(onClick = onClick) else modifier
    Card(
        modifier  = rootModifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = elevation),
        colors    = CardDefaults.cardColors(containerColor = containerColor),
        shape     = MaterialTheme.shapes.large,
    ) {
        Column(modifier = Modifier.padding(contentPadding), content = { content() })
    }
}

/**
 * Card variant used for active-emergency surfaces. Red background, elevated
 * above all other UI, no interactive affordance by default.
 */
@Composable
fun AmanahEmergencyCard(
    modifier: Modifier = Modifier,
    contentPadding: Dp = AmanahSpacing.md,
    content: @Composable () -> Unit,
) {
    Card(
        modifier  = modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = AmanahElevation.emergency),
        colors    = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
            contentColor   = MaterialTheme.colorScheme.onErrorContainer,
        ),
        shape     = MaterialTheme.shapes.large,
    ) {
        Column(modifier = Modifier.padding(contentPadding), content = { content() })
    }
}
