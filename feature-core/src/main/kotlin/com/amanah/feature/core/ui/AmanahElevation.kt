package com.amanah.feature.core.ui

import androidx.compose.ui.unit.dp

/**
 * Elevation tokens. Card / Surface elevations should reference these.
 *
 * Material 3 has five canonical levels (0–5); we expose a friendlier four:
 * none, low, md, high, xhi. Use [emergency] for the active-emergency banner /
 * floating SOS controls — these need to stand out above any normal stack.
 */
object AmanahElevation {
    val none = 0.dp
    val low  = 1.dp
    val md   = 2.dp
    val high = 4.dp
    val xhi  = 8.dp

    /** Reserved for active-emergency surfaces (always above other UI). */
    val emergency = 12.dp
}
