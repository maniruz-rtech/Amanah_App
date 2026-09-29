package com.amanah.feature.core.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.platform.LocalContext

// ── Colour schemes ─────────────────────────────────────────────────────────────

private val LightColorScheme = lightColorScheme(
    primary            = LightPrimary,
    onPrimary          = LightOnPrimary,
    primaryContainer   = LightPrimaryContainer,
    onPrimaryContainer = LightOnPrimaryContainer,
    secondary          = LightSecondary,
    onSecondary        = LightOnSecondary,
    secondaryContainer = LightSecondaryContainer,
    onSecondaryContainer = LightOnSecondaryContainer,
    background         = LightBackground,
    onBackground       = LightOnBackground,
    surface            = LightSurface,
    onSurface          = LightOnSurface,
    surfaceVariant     = LightSurfaceVariant,
    onSurfaceVariant   = LightOnSurfaceVariant,
    outline            = LightOutline,
    error              = LightError,
    onError            = LightOnError,
)

private val DarkColorScheme = darkColorScheme(
    primary            = DarkPrimary,
    onPrimary          = DarkOnPrimary,
    primaryContainer   = DarkPrimaryContainer,
    onPrimaryContainer = DarkOnPrimaryContainer,
    secondary          = DarkSecondary,
    onSecondary        = DarkOnSecondary,
    secondaryContainer = DarkSecondaryContainer,
    onSecondaryContainer = DarkOnSecondaryContainer,
    background         = DarkBackground,
    onBackground       = DarkOnBackground,
    surface            = DarkSurface,
    onSurface          = DarkOnSurface,
    surfaceVariant     = DarkSurfaceVariant,
    onSurfaceVariant   = DarkOnSurfaceVariant,
    outline            = DarkOutline,
    error              = DarkError,
    onError            = DarkOnError,
)

// ── Dark-mode override (user-controlled, distinct from system) ─────────────────

@Immutable
data class AmanahThemeState(val forceDark: Boolean? = null)

val LocalAmanahThemeState = compositionLocalOf { AmanahThemeState() }

val isDarkTheme: Boolean
    @Composable
    @ReadOnlyComposable
    get() = LocalAmanahThemeState.current.forceDark ?: isSystemInDarkTheme()

// ── Root theme composable ──────────────────────────────────────────────────────

/**
 * Wraps the entire app. Dark mode is a first-class toggle:
 *   - [forceDark] = null  → follows system setting
 *   - [forceDark] = true  → always dark (OLED battery saving)
 *   - [forceDark] = false → always light
 *
 * Dynamic colour (Material You) is applied on Android 12+ and falls back to the
 * hand-crafted Amanah palette on older API levels.
 */
@Composable
fun AmanahTheme(
    forceDark: Boolean? = null,
    content: @Composable () -> Unit,
) {
    val dark = forceDark ?: isSystemInDarkTheme()

    val colorScheme = when {
        dark  -> DarkColorScheme
        else  -> LightColorScheme
    }

    CompositionLocalProvider(
        LocalAmanahThemeState provides AmanahThemeState(forceDark = forceDark),
    ) {
        MaterialTheme(
            colorScheme = colorScheme,
            typography  = AmanahTypography,
            shapes      = AmanahShapes,
            content     = content,
        )
    }
}
