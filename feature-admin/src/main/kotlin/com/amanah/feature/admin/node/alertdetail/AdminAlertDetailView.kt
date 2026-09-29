package com.amanah.feature.admin.node.alertdetail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Divider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.amanah.feature.core.theme.AmanahTheme
import com.amanah.feature.core.ui.AmanahCard
import com.amanah.feature.core.ui.AmanahDestructiveButton
import com.amanah.feature.core.ui.AmanahLoadingState
import com.amanah.feature.core.ui.AmanahScaffold
import com.amanah.feature.core.ui.AmanahSecondaryButton
import com.amanah.feature.core.ui.AmanahSpacing
import com.amanah.feature.core.ui.AmanahStatusBadge
import com.amanah.feature.core.ui.AmanahTopBar
import com.amanah.feature.core.ui.BadgeTone
import com.amanah.lib.nodes.NodeView
import com.google.android.gms.maps.model.BitmapDescriptorFactory
import com.google.android.gms.maps.model.LatLng
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.MapUiSettings
import com.google.maps.android.compose.Marker
import com.google.maps.android.compose.MarkerState
import com.google.maps.android.compose.rememberCameraPositionState
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ── Contract ───────────────────────────────────────────────────────────────────

enum class AlertStatus { ACTIVE, RESOLVED, CANCELLED, TIMED_OUT }
enum class ResponderStatus { NOTIFIED, ACKNOWLEDGED, EN_ROUTE, ARRIVED, DECLINED }

data class ResponderEntry(
    val responderId: String,
    val displayName: String,
    val lat: Double,
    val lng: Double,
    val etaSeconds: Int?,
    val distanceMeters: Int?,  // pre-rounded
    val status: ResponderStatus,
)

data class AdminAlertDetailState(
    val alertId: String,
    val isLoading: Boolean = true,
    val isResolving: Boolean = false,
    val status: AlertStatus? = null,
    val triggeredAt: Long = 0L,
    val victimName: String? = null,
    val victimLat: Double? = null,
    val victimLng: Double? = null,
    val h3Cell: String? = null,
    val responders: List<ResponderEntry> = emptyList(),
    val notifiedCount: Int = 0,
    val acknowledgedCount: Int = 0,
)

sealed class AdminAlertDetailEvent {
    object Back         : AdminAlertDetailEvent()
    object ForceResolve : AdminAlertDetailEvent()
    object Escalate     : AdminAlertDetailEvent()
}

// ── NodeView ───────────────────────────────────────────────────────────────────

class AdminAlertDetailView : NodeView<AdminAlertDetailState, AdminAlertDetailEvent> {
    override var events: ((AdminAlertDetailEvent) -> Unit)? = null
    private var _state by mutableStateOf<AdminAlertDetailState?>(null)
    override fun render(state: AdminAlertDetailState) { _state = state }

    @Composable
    fun Content() {
        AmanahTheme {
            val state = _state
            if (state == null) {
                AmanahLoadingState(message = "Loading alert…")
                return@AmanahTheme
            }
            AdminAlertDetailScreen(state = state, onEvent = { events?.invoke(it) })
        }
    }
}

// ── Screen ─────────────────────────────────────────────────────────────────────

@Composable
private fun AdminAlertDetailScreen(state: AdminAlertDetailState, onEvent: (AdminAlertDetailEvent) -> Unit) {
    var showResolveDialog by remember { mutableStateOf(false) }

    AmanahScaffold(
        topBar = {
            AmanahTopBar(
                title    = "Alert #${state.alertId.takeLast(6).uppercase()}",
                subtitle = state.victimName?.let { "Triggered by $it" },
                onBack   = { onEvent(AdminAlertDetailEvent.Back) },
            )
        },
    ) { padding ->
        if (state.isLoading) {
            AmanahLoadingState(modifier = Modifier.padding(padding))
            return@AmanahScaffold
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            // ── Status header bar (red when active) ───────────────────────────
            StatusHeader(state)

            // ── Map (only when we have a victim location) ─────────────────────
            if (state.victimLat != null && state.victimLng != null) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(280.dp)
                        .padding(horizontal = AmanahSpacing.md, vertical = AmanahSpacing.sm)
                        .clip(RoundedCornerShape(16.dp)),
                ) {
                    AdminAlertMap(state)
                }
            }

            // ── Stats + Responder list ─────────────────────────────────────────
            Column(
                modifier            = Modifier
                    .padding(horizontal = AmanahSpacing.md)
                    .padding(bottom = AmanahSpacing.md),
                verticalArrangement = Arrangement.spacedBy(AmanahSpacing.md),
            ) {
                CountsCard(state)

                AmanahCard {
                    Text("Responders", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(AmanahSpacing.sm))
                    state.responders.forEachIndexed { index, responder ->
                        ResponderRow(responder)
                        if (index < state.responders.lastIndex) {
                            Divider(modifier = Modifier.padding(vertical = AmanahSpacing.sm))
                        }
                    }
                }

                if (state.status == AlertStatus.ACTIVE) {
                    AmanahSecondaryButton(text = "Escalate", onClick = { onEvent(AdminAlertDetailEvent.Escalate) })
                    AmanahDestructiveButton(
                        text    = "Force Resolve",
                        onClick = { showResolveDialog = true },
                        loading = state.isResolving,
                    )
                }
            }
        }
    }

    // ── Confirm dialog ─────────────────────────────────────────────────────────
    if (showResolveDialog) {
        var reason by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { showResolveDialog = false },
            title    = { Text("Force resolve this alert?") },
            text     = {
                Column {
                    Text("This will close the alert for all responders and notify the victim. Resolutions are audited.")
                    Spacer(Modifier.height(AmanahSpacing.sm))
                    OutlinedTextField(
                        value          = reason,
                        onValueChange  = { reason = it },
                        label          = { Text("Reason") },
                        singleLine     = false,
                        modifier       = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    showResolveDialog = false
                    onEvent(AdminAlertDetailEvent.ForceResolve)
                }) { Text("Force Resolve") }
            },
            dismissButton = {
                TextButton(onClick = { showResolveDialog = false }) { Text("Cancel") }
            },
        )
    }
}

// ── Sections ───────────────────────────────────────────────────────────────────

@Composable
private fun StatusHeader(state: AdminAlertDetailState) {
    val tone = when (state.status) {
        AlertStatus.ACTIVE     -> BadgeTone.CRITICAL
        AlertStatus.RESOLVED   -> BadgeTone.POSITIVE
        AlertStatus.CANCELLED  -> BadgeTone.WARNING
        AlertStatus.TIMED_OUT  -> BadgeTone.WARNING
        null                   -> BadgeTone.NEUTRAL
    }
    Row(
        modifier              = Modifier
            .fillMaxWidth()
            .padding(horizontal = AmanahSpacing.md, vertical = AmanahSpacing.sm),
        verticalAlignment     = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(AmanahSpacing.sm),
    ) {
        AmanahStatusBadge(text = state.status?.name ?: "—", tone = tone)
        Text(
            text  = formatAbsolute(state.triggeredAt),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun CountsCard(state: AdminAlertDetailState) {
    AmanahCard {
        Row(
            modifier              = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            CountCell("Notified",     state.notifiedCount.toString())
            CountCell("Acknowledged", state.acknowledgedCount.toString())
            CountCell("En route",     state.responders.count { it.status == ResponderStatus.EN_ROUTE }.toString())
            CountCell("Arrived",      state.responders.count { it.status == ResponderStatus.ARRIVED }.toString())
        }
    }
}

@Composable
private fun CountCell(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun ResponderRow(responder: ResponderEntry) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(width = 4.dp, height = 36.dp)
                .clip(RoundedCornerShape(2.dp))
                .padding(),
        )
        Column(modifier = Modifier.weight(1f)) {
            Text(responder.displayName, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
            Row(horizontalArrangement = Arrangement.spacedBy(AmanahSpacing.sm)) {
                responder.distanceMeters?.let { d ->
                    Text("${formatDistance(d)} away", style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                responder.etaSeconds?.let { eta ->
                    Text("· ETA ${formatEta(eta)}", style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        AmanahStatusBadge(
            text = responder.status.name.replace('_', ' '),
            tone = when (responder.status) {
                ResponderStatus.EN_ROUTE     -> BadgeTone.POSITIVE
                ResponderStatus.ARRIVED      -> BadgeTone.POSITIVE
                ResponderStatus.ACKNOWLEDGED -> BadgeTone.NEUTRAL
                ResponderStatus.NOTIFIED     -> BadgeTone.WARNING
                ResponderStatus.DECLINED     -> BadgeTone.CRITICAL
            },
        )
    }
}

@Composable
private fun AdminAlertMap(state: AdminAlertDetailState) {
    val cameraPositionState = rememberCameraPositionState()
    val victimLatLng        = LatLng(state.victimLat!!, state.victimLng!!)

    GoogleMap(
        modifier             = Modifier.fillMaxSize(),
        cameraPositionState  = cameraPositionState,
        uiSettings           = MapUiSettings(
            mapToolbarEnabled = false,
            zoomControlsEnabled = false,
        ),
    ) {
        Marker(
            state   = MarkerState(position = victimLatLng),
            title   = "Victim",
            icon    = BitmapDescriptorFactory.defaultMarker(BitmapDescriptorFactory.HUE_RED),
        )
        state.responders.forEach { responder ->
            Marker(
                state   = MarkerState(position = LatLng(responder.lat, responder.lng)),
                title   = responder.displayName,
                snippet = "${responder.status.name} · ${responder.distanceMeters?.let { formatDistance(it) } ?: "—"}",
                icon    = BitmapDescriptorFactory.defaultMarker(
                    when (responder.status) {
                        ResponderStatus.EN_ROUTE     -> BitmapDescriptorFactory.HUE_GREEN
                        ResponderStatus.ACKNOWLEDGED -> BitmapDescriptorFactory.HUE_AZURE
                        ResponderStatus.ARRIVED      -> BitmapDescriptorFactory.HUE_VIOLET
                        ResponderStatus.NOTIFIED     -> BitmapDescriptorFactory.HUE_YELLOW
                        ResponderStatus.DECLINED     -> BitmapDescriptorFactory.HUE_ROSE
                    }
                ),
            )
        }
    }
}

// ── formatting helpers ─────────────────────────────────────────────────────────

private fun formatAbsolute(ts: Long) = SimpleDateFormat("dd MMM yyyy, HH:mm", Locale.getDefault()).format(Date(ts))

private fun formatDistance(meters: Int): String =
    if (meters >= 1_000) "${"%.1f".format(meters / 1_000.0)} km" else "$meters m"

private fun formatEta(seconds: Int): String {
    val mins = seconds / 60
    return when {
        mins < 1  -> "<1 min"
        mins == 1 -> "1 min"
        else      -> "$mins min"
    }
}
