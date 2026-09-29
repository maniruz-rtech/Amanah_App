package com.amanah.feature.core.ui

import androidx.compose.ui.unit.dp

/**
 * Centralised spacing tokens. All `.padding(...)` and `Arrangement.spacedBy(...)`
 * call sites should pull from this object instead of using raw `.dp` literals.
 *
 * Scale follows an 8 dp base grid with a half-step (4 dp) and a half-of-half
 * step (2 dp) for tight composition (icons next to text, chips, etc.).
 */
object AmanahSpacing {
    val zero = 0.dp
    val xxs  = 2.dp
    val xs   = 4.dp
    val sm   = 8.dp
    val md   = 16.dp
    val lg   = 24.dp
    val xl   = 32.dp
    val xxl  = 48.dp
    val xxxl = 64.dp

    /** Screen-edge gutter used by every `Scaffold` body. */
    val gutter = md

    /** Vertical spacing between two stacked top-level sections. */
    val section = lg
}
