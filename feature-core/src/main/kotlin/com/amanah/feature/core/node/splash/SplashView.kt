package com.amanah.feature.core.node.splash

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.EaseOutCubic
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.amanah.feature.core.theme.AmanahGreen
import com.amanah.feature.core.theme.AmanahGreenDark
import com.amanah.feature.core.theme.AmanahTheme
import com.amanah.lib.nodes.NodeView
import kotlinx.coroutines.delay

// ── Contract ───────────────────────────────────────────────────────────────────

data class SplashState(val animationComplete: Boolean = false)

sealed class SplashEvent {
    object AnimationComplete : SplashEvent()
}

// ── NodeView implementation ────────────────────────────────────────────────────

class SplashView : NodeView<SplashState, SplashEvent> {

    override var events: ((SplashEvent) -> Unit)? = null

    private var _state by mutableStateOf(SplashState())

    override fun render(state: SplashState) {
        _state = state
    }

    @Composable
    fun Content() {
        AmanahTheme {
            SplashScreen(
                onAnimationComplete = { events?.invoke(SplashEvent.AnimationComplete) }
            )
        }
    }
}

// ── Compose UI ─────────────────────────────────────────────────────────────────

@Composable
private fun SplashScreen(onAnimationComplete: () -> Unit) {
    val scale = remember { Animatable(0.6f) }
    val alpha = remember { Animatable(0f) }

    LaunchedEffect(Unit) {
        scale.animateTo(1f, animationSpec = tween(700, easing = EaseOutCubic))
        alpha.animateTo(1f, animationSpec = tween(400))
        delay(800)
        onAnimationComplete()
    }

    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    colors = listOf(AmanahGreen, AmanahGreenDark),
                )
            ),
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {

            // Logo mark — a stylised Arabic ع rendered via text; swap for
            // ImageVector / SVG asset when the brand asset is available.
            Text(
                text = "أ",
                fontSize = 96.sp,
                color = androidx.compose.ui.graphics.Color.White,
                modifier = Modifier
                    .scale(scale.value)
                    .alpha(alpha.value),
            )

            Spacer(Modifier.height(16.dp))

            Text(
                text = "Amanah",
                style = MaterialTheme.typography.displayMedium.copy(
                    color = androidx.compose.ui.graphics.Color.White,
                    fontWeight = FontWeight.Bold,
                ),
                modifier = Modifier.alpha(alpha.value),
            )

            Spacer(Modifier.height(8.dp))

            Text(
                text = "Your trusted companion",
                style = MaterialTheme.typography.bodyLarge.copy(
                    color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.80f),
                ),
                modifier = Modifier.alpha(alpha.value),
            )
        }
    }
}
