package com.amanah.feature.core.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/**
 * Branded top bar.
 *
 *   - [title]            : Required main title.
 *   - [subtitle]         : Optional smaller line under the title.
 *   - [onBack]           : If non-null, renders an Arrow-Back navigation icon.
 *   - [actions]          : Trailing icons (notifications, dark-mode toggle, etc.).
 *
 * Respects status-bar inset.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AmanahTopBar(
    title: String,
    subtitle: String? = null,
    onBack: (() -> Unit)? = null,
    actions: @Composable () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    TopAppBar(
        title = {
            Column {
                Text(
                    text  = title,
                    style = MaterialTheme.typography.titleLarge,
                )
                if (subtitle != null) {
                    Text(
                        text  = subtitle,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                    )
                }
            }
        },
        navigationIcon = {
            if (onBack != null) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                }
            }
        },
        actions = { actions() },
        colors  = TopAppBarDefaults.topAppBarColors(
            containerColor = MaterialTheme.colorScheme.surface,
        ),
        modifier = modifier.statusBarsPadding(),
    )
}
