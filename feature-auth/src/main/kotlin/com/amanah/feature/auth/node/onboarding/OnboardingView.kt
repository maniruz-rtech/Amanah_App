package com.amanah.feature.auth.node.onboarding

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.PrivacyTip
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.amanah.feature.core.theme.AmanahTheme
import com.amanah.feature.core.ui.AmanahMotion
import com.amanah.feature.core.ui.AmanahPrimaryButton
import com.amanah.feature.core.ui.AmanahSpacing
import com.amanah.lib.nodes.NodeView

// ── Contract ───────────────────────────────────────────────────────────────────

data class OnboardingState(val pageIndex: Int = 0) {
    val isLastPage: Boolean get() = pageIndex == PAGES_LAST_INDEX
    companion object { const val PAGES_LAST_INDEX = 2 }
}

sealed class OnboardingEvent {
    object Next : OnboardingEvent()
    object Skip : OnboardingEvent()
}

private data class OnboardingPage(
    val icon: ImageVector,
    val title: String,
    val body: String,
)

private val PAGES = listOf(
    OnboardingPage(
        icon  = Icons.Default.Groups,
        title = "Welcome to Amanah",
        body  = "A safety network of trusted neighbours. Help is one tap away from the people closest to you.",
    ),
    OnboardingPage(
        icon  = Icons.Default.Warning,
        title = "One tap for help",
        body  = "Long-press the emergency button and verified members nearby are notified instantly. We'll show responders on the map and live ETA.",
    ),
    OnboardingPage(
        icon  = Icons.Default.PrivacyTip,
        title = "Privacy by design",
        body  = "Your location is always blurred (±500m–1km) unless you trigger an emergency. Exact coordinates are only shared with assigned responders, and only while the alert is active.",
    ),
)

// ── NodeView ───────────────────────────────────────────────────────────────────

class OnboardingView : NodeView<OnboardingState, OnboardingEvent> {
    override var events: ((OnboardingEvent) -> Unit)? = null
    private var _state by mutableStateOf(OnboardingState())
    override fun render(state: OnboardingState) { _state = state }

    @Composable
    fun Content() {
        AmanahTheme {
            OnboardingScreen(state = _state, onEvent = { events?.invoke(it) })
        }
    }
}

// ── UI ─────────────────────────────────────────────────────────────────────────

@Composable
private fun OnboardingScreen(state: OnboardingState, onEvent: (OnboardingEvent) -> Unit) {
    val page = PAGES[state.pageIndex.coerceIn(0, PAGES.lastIndex)]

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding(),
    ) {
        // ── Skip button (top-right) ─────────────────────────────────────────────
        TextButton(
            onClick  = { onEvent(OnboardingEvent.Skip) },
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(AmanahSpacing.sm),
        ) {
            Text("Skip", style = MaterialTheme.typography.labelLarge)
        }

        // ── Page content ────────────────────────────────────────────────────────
        AnimatedContent(
            targetState    = state.pageIndex,
            transitionSpec = {
                (slideInHorizontally(AmanahMotion.normalTween()) { it / 3 } + fadeIn())
                    .togetherWith(slideOutHorizontally(AmanahMotion.normalTween()) { -it / 3 } + fadeOut())
            },
            label    = "OnboardingPage",
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = AmanahSpacing.lg),
        ) { _ ->
            Column(
                modifier              = Modifier.fillMaxSize(),
                horizontalAlignment   = Alignment.CenterHorizontally,
                verticalArrangement   = Arrangement.Center,
            ) {
                Icon(
                    imageVector        = page.icon,
                    contentDescription = null,
                    tint               = MaterialTheme.colorScheme.primary,
                    modifier           = Modifier.size(96.dp),
                )
                Spacer(Modifier.height(AmanahSpacing.lg))
                Text(
                    text       = page.title,
                    style      = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Bold),
                    color      = MaterialTheme.colorScheme.onBackground,
                    textAlign  = TextAlign.Center,
                )
                Spacer(Modifier.height(AmanahSpacing.md))
                Text(
                    text       = page.body,
                    style      = MaterialTheme.typography.bodyLarge,
                    color      = MaterialTheme.colorScheme.onSurfaceVariant,
                    textAlign  = TextAlign.Center,
                )
            }
        }

        // ── Footer (page indicator + next/get started) ─────────────────────────
        Column(
            modifier              = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .padding(horizontal = AmanahSpacing.lg, vertical = AmanahSpacing.lg)
                .navigationBarsPadding(),
            horizontalAlignment   = Alignment.CenterHorizontally,
            verticalArrangement   = Arrangement.spacedBy(AmanahSpacing.md),
        ) {
            PageIndicator(current = state.pageIndex, total = PAGES.size)
            AmanahPrimaryButton(
                text    = if (state.isLastPage) "Get Started" else "Next",
                onClick = { onEvent(OnboardingEvent.Next) },
            )
        }
    }
}

@Composable
private fun PageIndicator(current: Int, total: Int) {
    Row(horizontalArrangement = Arrangement.spacedBy(AmanahSpacing.xs)) {
        repeat(total) { index ->
            val isActive = index == current
            Box(
                modifier = Modifier
                    .height(8.dp)
                    .width(if (isActive) 24.dp else 8.dp)
                    .background(
                        color = if (isActive) MaterialTheme.colorScheme.primary
                                else MaterialTheme.colorScheme.outline.copy(alpha = 0.3f),
                        shape = CircleShape,
                    ),
            )
        }
    }
}
