package com.amanah.feature.core.ui

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.Easing
import androidx.compose.animation.core.tween

/**
 * Motion tokens — durations and easings. Compose `tween()` and `animateTo()`
 * call sites should pull from here.
 *
 * Durations follow Material Motion guidance:
 *   - FAST   (150 ms) → micro-interactions (toggles, ripples)
 *   - NORMAL (300 ms) → screen-element transitions (cards, sheets)
 *   - SLOW   (600 ms) → screen-level transitions (route changes)
 *
 * Use [reduceMotion] for users with Settings.Global.TRANSITION_ANIMATION_SCALE = 0;
 * collapsing to a 0-duration tween prevents pointless re-renders.
 */
object AmanahMotion {
    const val FAST   = 150
    const val NORMAL = 300
    const val SLOW   = 600

    /** A drop-in alias for animate*AsState(animationSpec = tween(...)). */
    fun <T> fastTween()   = tween<T>(durationMillis = FAST,   easing = EaseStandard)
    fun <T> normalTween() = tween<T>(durationMillis = NORMAL, easing = EaseStandard)
    fun <T> slowTween()   = tween<T>(durationMillis = SLOW,   easing = EaseEmphasis)

    /** Material 3 "Easing.Standard" — most general-purpose curve. */
    val EaseStandard: Easing = CubicBezierEasing(0.2f, 0.0f, 0.0f, 1.0f)

    /** Material 3 "Easing.Emphasized" — for high-prominence transitions. */
    val EaseEmphasis: Easing = CubicBezierEasing(0.05f, 0.7f, 0.1f, 1.0f)

    /** Emphasized accelerate — for content disappearing offscreen. */
    val EaseExit:     Easing = CubicBezierEasing(0.3f, 0.0f, 0.8f, 0.15f)
}
