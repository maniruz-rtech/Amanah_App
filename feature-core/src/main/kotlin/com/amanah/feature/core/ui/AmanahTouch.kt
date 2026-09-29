package com.amanah.feature.core.ui

import androidx.compose.ui.unit.dp

/**
 * Touch-target tokens. Material/Android accessibility guidance requires a
 * minimum 48 dp × 48 dp interactive area.
 */
object AmanahTouch {
    /** Minimum touch target for any tappable element (WCAG / Material). */
    val MIN_TOUCH_TARGET = 48.dp

    /** Standard button height. */
    val BUTTON_HEIGHT = 52.dp

    /** Standard input-field height. */
    val INPUT_HEIGHT  = 56.dp

    /** Pulsing emergency button — must dominate the screen. */
    val EMERGENCY_BUTTON_SIZE = 160.dp
}
