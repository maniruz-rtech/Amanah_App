package com.amanah.feature.user.node.dashboard

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.DarkMode
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.LightMode
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledIconToggleButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.amanah.feature.core.theme.AmanahTheme
import com.amanah.feature.user.mvi.AlertSummary
import com.amanah.feature.user.mvi.NearbyUser
import com.amanah.feature.user.mvi.UserState
import com.amanah.feature.user.mvi.UserWish
import com.amanah.lib.nodes.NodeView
import com.badoo.mobile.util.WeakHandler

typealias UserEvent = UserWish

class UserDashboardView(
    private val weakHandler: WeakHandler = WeakHandler(),
) : NodeView<UserState, UserEvent> {

    override var events: ((UserEvent) -> Unit)? = null

    private var _state by mutableStateOf(UserState())

    override fun render(state: UserState) { _state = state }

    @Composable
    fun Content() {
        AmanahTheme(forceDark = if (_state.isDarkMode) true else null) {
            // ── Incoming emergency takes full screen immediately ────────────────
            if (_state.emergencyActive && _state.victimLat != null) {
                IncomingEmergencyScreen(
                    state       = _state,
                    weakHandler = weakHandler,
                    onEvent     = { events?.invoke(it) },
                )
            } else {
                UserDashboardScreen(state = _state, onEvent = { events?.invoke(it) })
            }
        }
    }
}

// ── Main dashboard scaffold ────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun UserDashboardScreen(state: UserState, onEvent: (UserEvent) -> Unit) {
    val snackbar = remember { SnackbarHostState() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        "Amanah",
                        style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold),
                        color = MaterialTheme.colorScheme.primary,
                    )
                },
                actions = {
                    FilledIconToggleButton(
                        checked  = state.isDarkMode,
                        onCheckedChange = { onEvent(UserWish.ToggleDarkMode) },
                    ) {
                        Icon(
                            imageVector = if (state.isDarkMode) Icons.Default.DarkMode else Icons.Default.LightMode,
                            contentDescription = if (state.isDarkMode) "Switch to light mode" else "Switch to dark mode",
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
                modifier = Modifier.statusBarsPadding(),
            )
        },
        bottomBar = {
            UserBottomNav(
                selected = state.tab,
                onSelect = { onEvent(UserWish.SelectTab(it)) },
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        AnimatedContent(
            targetState = state.tab,
            transitionSpec = { fadeIn().togetherWith(fadeOut()) },
            modifier = Modifier.fillMaxSize().padding(padding),
            label = "UserTabContent",
        ) { tab ->
            when (tab) {
                UserState.Tab.HOME     -> HomeTab(state, onEvent)
                UserState.Tab.ALERTS   -> AlertsTab(state.alertHistory)
                UserState.Tab.PROFILE  -> ProfileTab(state, onEvent)
                UserState.Tab.SETTINGS -> SettingsTab(state, onEvent)
            }
        }
    }
}

// ── Bottom nav ─────────────────────────────────────────────────────────────────

@Composable
private fun UserBottomNav(selected: UserState.Tab, onSelect: (UserState.Tab) -> Unit) {
    NavigationBar {
        NavigationBarItem(selected == UserState.Tab.HOME,   { onSelect(UserState.Tab.HOME) },
            { Icon(Icons.Default.Home, "Home") },   label = { Text("Home") })
        NavigationBarItem(selected == UserState.Tab.ALERTS, { onSelect(UserState.Tab.ALERTS) },
            { Icon(Icons.Default.History, "Alerts") }, label = { Text("Alerts") })
        NavigationBarItem(selected == UserState.Tab.PROFILE, { onSelect(UserState.Tab.PROFILE) },
            { Icon(Icons.Default.AccountCircle, "Profile") }, label = { Text("Profile") })
        NavigationBarItem(selected == UserState.Tab.SETTINGS, { onSelect(UserState.Tab.SETTINGS) },
            { Icon(Icons.Default.Settings, "Settings") }, label = { Text("Settings") })
    }
}

// ── Home tab (Nearby grid + Emergency Button) ──────────────────────────────────

@Composable
private fun HomeTab(state: UserState, onEvent: (UserEvent) -> Unit) {
    Column(Modifier.fillMaxSize()) {

        // ── EMERGENCY BUTTON — always visible, thumb-reachable at bottom ───────
        EmergencyButton(
            active  = state.emergencyActive,
            onTrigger = { onEvent(UserWish.TriggerEmergency) },
            onCancel  = { onEvent(UserWish.CancelEmergency) },
            modifier  = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 16.dp),
        )

        // ── Nearby users grid ─────────────────────────────────────────────────
        Text(
            text     = "Nearby Active Members",
            style    = MaterialTheme.typography.titleSmall,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
        Spacer(Modifier.height(8.dp))

        if (state.isLoadingNearby) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp),
                verticalArrangement   = Arrangement.spacedBy(8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(state.nearbyUsers, key = { it.userId }) { user ->
                    NearbyUserCard(user)
                }
            }
        }
    }
}

@Composable
private fun NearbyUserCard(user: NearbyUser) {
    Card(
        modifier  = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(1.dp),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(user.displayName, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Medium)
            Text(
                if (user.isExact) "Exact location" else "~Nearby (approx.)",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

// ── Emergency Button ──────────────────────────────────────────────────────────

/**
 * Pulsing emergency button that requires a long-press (~1.5 s) to prevent
 * accidental triggers. Provides haptic feedback at press start and on confirm.
 *
 * Privacy invariant: this button NEVER displays or logs GPS coordinates.
 * Location is captured inside the EmergencyAlertEngine when the alert fires.
 */
@Composable
private fun EmergencyButton(
    active: Boolean,
    onTrigger: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val haptic = LocalHapticFeedback.current
    val infiniteTransition = rememberInfiniteTransition(label = "EmergencyPulse")
    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 1f, targetValue = 1.12f,
        animationSpec = infiniteRepeatable(tween(700), RepeatMode.Reverse),
        label = "PulseScale",
    )

    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        if (!active) {
            // ── Idle: prominent red CTA ─────────────────────────────────────
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier
                    .size(160.dp)
                    .scale(pulseScale)
                    .background(
                        color = MaterialTheme.colorScheme.error,
                        shape = CircleShape,
                    )
                    .pointerInput(Unit) {
                        detectTapGestures(
                            onLongPress = {
                                haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                                onTrigger()
                            },
                            onPress = {
                                haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                            },
                        )
                    },
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.Warning, null, tint = Color.White, modifier = Modifier.size(40.dp))
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = "EMERGENCY",
                        color = Color.White,
                        fontWeight = FontWeight.ExtraBold,
                        fontSize = 14.sp,
                    )
                    Text(
                        text = "Hold to trigger",
                        color = Color.White.copy(alpha = 0.8f),
                        fontSize = 10.sp,
                    )
                }
            }
        } else {
            // ── Active emergency: cancel affordance ─────────────────────────
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Card(
                    colors   = CardDefaults.cardColors(MaterialTheme.colorScheme.errorContainer),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        Modifier.padding(16.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Default.Warning, null, tint = MaterialTheme.colorScheme.error)
                        Text(
                            "Emergency alert ACTIVE — Responders notified",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                }
                OutlinedButton(onClick = onCancel) { Text("Cancel Emergency") }
            }
        }
    }
}

// ── Alerts tab ─────────────────────────────────────────────────────────────────

@Composable
private fun AlertsTab(alerts: List<AlertSummary>) {
    if (alerts.isEmpty()) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("No alert history", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        return
    }
    LazyColumn(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items(alerts, key = { it.alertId }) { alert ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text("Alert #${alert.alertId.takeLast(6).uppercase()}", style = MaterialTheme.typography.titleSmall)
                    Text(alert.statusLabel, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (alert.wasResponder) Text("You were a responder",
                        style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                }
            }
        }
    }
}

// ── Profile tab ────────────────────────────────────────────────────────────────

@Composable
private fun ProfileTab(state: UserState, onEvent: (UserEvent) -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Icon(Icons.Default.AccountCircle, null, modifier = Modifier.size(80.dp),
            tint = MaterialTheme.colorScheme.primary)
        Text(state.currentUser?.displayName ?: "—", style = MaterialTheme.typography.headlineSmall)
        Text(state.currentUser?.email ?: "—", style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text("Role: ${state.currentUser?.role?.name ?: "—"}", style = MaterialTheme.typography.labelMedium)
        Spacer(Modifier.weight(1f))
        Button(
            onClick  = { onEvent(UserWish.Logout) },
            colors   = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Sign Out") }
    }
}

// ── Settings tab ───────────────────────────────────────────────────────────────

@Composable
private fun SettingsTab(state: UserState, onEvent: (UserEvent) -> Unit) {
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Appearance", style = MaterialTheme.typography.titleMedium)
        Card(modifier = Modifier.fillMaxWidth()) {
            Row(
                Modifier.padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Dark Mode", style = MaterialTheme.typography.bodyMedium)
                FilledIconToggleButton(
                    checked = state.isDarkMode,
                    onCheckedChange = { onEvent(UserWish.ToggleDarkMode) },
                ) {
                    Icon(
                        imageVector = if (state.isDarkMode) Icons.Default.DarkMode else Icons.Default.LightMode,
                        contentDescription = if (state.isDarkMode) "Switch to light mode" else "Switch to dark mode",
                    )
                }
            }
        }
        Text(
            "Privacy: Your location is always obfuscated (±500m–1km) unless an active emergency is in progress.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Start,
        )
    }
}

// ── Full-screen incoming emergency overlay ─────────────────────────────────────

/**
 * Full-screen overlay shown when this device receives a confirmed, in-range
 * emergency alert. Exact victim coordinates are passed here only because
 * [EmergencyState.isActiveEmergency] is true — [LocationPrivacyFilter.reveal]
 * governs the privacy boundary upstream.
 *
 * Layout (top → bottom):
 *   1. Alert header bar (red background, warning icon, title)
 *   2. [ResponderMapView] — Google Maps with victim anchor + responder markers
 *   3. [EtaCard] — nearest responder distance + ETA (hidden until first update)
 *   4. Dismiss / alert metadata footer
 */
@Composable
private fun IncomingEmergencyScreen(
    state: UserState,
    weakHandler: WeakHandler,
    onEvent: (UserEvent) -> Unit,
) {
    val victimLat = state.victimLat ?: return
    val victimLng = state.victimLng ?: return

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        // ── Header bar ────────────────────────────────────────────────────────
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.error)
                .statusBarsPadding()
                .padding(horizontal = 20.dp, vertical = 14.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Icon(
                    Icons.Default.Warning, null,
                    tint     = Color.White,
                    modifier = Modifier.size(28.dp),
                )
                Column {
                    Text(
                        "EMERGENCY ALERT",
                        style      = MaterialTheme.typography.titleMedium.copy(
                            fontWeight = FontWeight.ExtraBold,
                            color      = Color.White,
                        ),
                    )
                    Text(
                        "Alert #${state.emergencyAlertId?.takeLast(6)?.uppercase() ?: "—"}",
                        style = MaterialTheme.typography.labelSmall.copy(color = Color.White.copy(alpha = 0.8f)),
                    )
                }
            }
        }

        // ── Google Maps — victim anchor + responder markers ───────────────────
        // Clipped to a rounded card shape for a polished emergency UI.
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .padding(horizontal = 12.dp, vertical = 8.dp)
                .clip(RoundedCornerShape(16.dp)),
        ) {
            ResponderMapView(
                victimLat   = victimLat,
                victimLng   = victimLng,
                responders  = state.responders,
                weakHandler = weakHandler,
                modifier    = Modifier.fillMaxSize(),
            )
        }

        // ── ETA card — shown once the nearest responder sends a location ──────
        if (state.responderEtaSeconds != null || state.responderDistanceMeters != null) {
            EtaCard(
                etaSeconds      = state.responderEtaSeconds,
                distanceMeters  = state.responderDistanceMeters,
                modifier        = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp),
            )
            Spacer(Modifier.height(8.dp))
        }

        // ── Footer — help text + dismiss ──────────────────────────────────────
        Column(
            modifier            = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp, vertical = 12.dp)
                .navigationBarsPadding(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                "Navigate to the victim's location immediately.\nAll distances rounded for privacy.",
                style       = MaterialTheme.typography.bodySmall,
                color       = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign   = TextAlign.Center,
            )
            OutlinedButton(
                onClick  = { onEvent(UserWish.CancelEmergency) },
                modifier = Modifier.fillMaxWidth(),
                colors   = ButtonDefaults.outlinedButtonColors(
                    contentColor = MaterialTheme.colorScheme.error,
                ),
            ) { Text("Dismiss Alert") }
        }
    }
}
