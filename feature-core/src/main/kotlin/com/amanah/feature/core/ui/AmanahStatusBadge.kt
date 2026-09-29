package com.amanah.feature.core.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight

/**
 * A small status pill — used wherever a state ("ACTIVE", "RESOLVED",
 * "PENDING APPROVAL", "SUSPENDED") needs to be highlighted with semantic colour.
 */
@Composable
fun AmanahStatusBadge(
    text: String,
    tone: BadgeTone = BadgeTone.NEUTRAL,
    modifier: Modifier = Modifier,
) {
    val container = when (tone) {
        BadgeTone.NEUTRAL  -> MaterialTheme.colorScheme.surfaceVariant
        BadgeTone.POSITIVE -> MaterialTheme.colorScheme.primaryContainer
        BadgeTone.WARNING  -> MaterialTheme.colorScheme.secondaryContainer
        BadgeTone.CRITICAL -> MaterialTheme.colorScheme.errorContainer
    }
    val onContainer = when (tone) {
        BadgeTone.NEUTRAL  -> MaterialTheme.colorScheme.onSurfaceVariant
        BadgeTone.POSITIVE -> MaterialTheme.colorScheme.onPrimaryContainer
        BadgeTone.WARNING  -> MaterialTheme.colorScheme.onSecondaryContainer
        BadgeTone.CRITICAL -> MaterialTheme.colorScheme.onErrorContainer
    }

    Text(
        text     = text,
        style    = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.SemiBold),
        color    = onContainer,
        modifier = modifier
            .background(color = container, shape = RoundedCornerShape(50))
            .padding(PaddingValues(horizontal = AmanahSpacing.sm, vertical = AmanahSpacing.xxs)),
    )
}

enum class BadgeTone { NEUTRAL, POSITIVE, WARNING, CRITICAL }
