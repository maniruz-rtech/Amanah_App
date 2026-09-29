package com.amanah.feature.user.node.incidentdetail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Place
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.width
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.amanah.feature.core.theme.AmanahTheme
import com.amanah.feature.core.ui.AmanahCard
import com.amanah.feature.core.ui.AmanahLoadingState
import com.amanah.feature.core.ui.AmanahScaffold
import com.amanah.feature.core.ui.AmanahSpacing
import com.amanah.feature.core.ui.AmanahStatusBadge
import com.amanah.feature.core.ui.AmanahTopBar
import com.amanah.feature.core.ui.BadgeTone
import com.amanah.lib.nodes.NodeView
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ── Contract ───────────────────────────────────────────────────────────────────

enum class IncidentStatus { ACTIVE, RESOLVED, CANCELLED, TIMED_OUT }

data class IncidentEventEntry(
    val id: String,
    val label: String,
    val timestamp: Long,
)

data class IncidentDetailState(
    val alertId: String,
    val isLoading: Boolean = true,
    val status: IncidentStatus? = null,
    val triggeredAt: Long = 0L,
    val resolvedAt: Long? = null,
    val victimLat: Double? = null,
    val victimLng: Double? = null,
    val h3Cell: String? = null,
    val respondersNotified: Int = 0,
    val respondersAcknowledged: Int = 0,
    val resolutionNote: String? = null,
    val events: List<IncidentEventEntry> = emptyList(),
)

sealed class IncidentDetailEvent {
    object Back : IncidentDetailEvent()
}

// ── NodeView ───────────────────────────────────────────────────────────────────

class IncidentDetailView : NodeView<IncidentDetailState, IncidentDetailEvent> {
    override var events: ((IncidentDetailEvent) -> Unit)? = null
    private var _state by mutableStateOf<IncidentDetailState?>(null)

    override fun render(state: IncidentDetailState) { _state = state }

    @Composable
    fun Content() {
        AmanahTheme {
            val state = _state
            if (state == null) {
                AmanahLoadingState(message = "Loading incident…")
                return@AmanahTheme
            }
            IncidentDetailScreen(state = state, onEvent = { events?.invoke(it) })
        }
    }
}

// ── Screen ─────────────────────────────────────────────────────────────────────

@Composable
private fun IncidentDetailScreen(state: IncidentDetailState, onEvent: (IncidentDetailEvent) -> Unit) {
    AmanahScaffold(
        topBar = {
            AmanahTopBar(
                title    = "Alert #${state.alertId.takeLast(6).uppercase()}",
                subtitle = "Incident Detail",
                onBack   = { onEvent(IncidentDetailEvent.Back) },
            )
        },
    ) { padding ->
        if (state.isLoading) {
            AmanahLoadingState(message = "Loading incident…", modifier = Modifier.padding(padding))
            return@AmanahScaffold
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = AmanahSpacing.md, vertical = AmanahSpacing.md)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(AmanahSpacing.md),
        ) {
            StatusHeader(state)
            MetadataCard(state)
            ResponderCountCard(state)
            if (state.resolutionNote != null) ResolutionNoteCard(state.resolutionNote)
            TimelineCard(state.events)
        }
    }
}

// ── Sections ───────────────────────────────────────────────────────────────────

@Composable
private fun StatusHeader(state: IncidentDetailState) {
    val (label, tone) = when (state.status) {
        IncidentStatus.ACTIVE     -> "ACTIVE"     to BadgeTone.CRITICAL
        IncidentStatus.RESOLVED   -> "RESOLVED"   to BadgeTone.POSITIVE
        IncidentStatus.CANCELLED  -> "CANCELLED"  to BadgeTone.WARNING
        IncidentStatus.TIMED_OUT  -> "TIMED OUT"  to BadgeTone.WARNING
        null                      -> "—"          to BadgeTone.NEUTRAL
    }
    Row(
        verticalAlignment     = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(AmanahSpacing.sm),
    ) {
        AmanahStatusBadge(text = label, tone = tone)
        Text(
            text  = formatAbsolute(state.triggeredAt),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun MetadataCard(state: IncidentDetailState) {
    AmanahCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(AmanahSpacing.sm)) {
            Icon(Icons.Default.Place, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Column {
                Text("Location (H3 district cell)", style = MaterialTheme.typography.labelMedium)
                Text(state.h3Cell ?: "—", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Spacer(Modifier.height(AmanahSpacing.sm))
        Text(
            "Privacy: precise coordinates are not shown after the incident is resolved.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ResponderCountCard(state: IncidentDetailState) {
    AmanahCard {
        Row(
            modifier              = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            CountStat(label = "Notified",     value = state.respondersNotified.toString())
            CountStat(label = "Acknowledged", value = state.respondersAcknowledged.toString())
        }
    }
}

@Composable
private fun CountStat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Bold))
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun ResolutionNoteCard(note: String) {
    AmanahCard {
        Text("Resolution note", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(AmanahSpacing.xs))
        Text(note, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun TimelineCard(events: List<IncidentEventEntry>) {
    val fmt = remember { SimpleDateFormat("HH:mm:ss", Locale.getDefault()) }
    AmanahCard {
        Text("Timeline", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(AmanahSpacing.sm))
        events.forEachIndexed { index, event ->
            TimelineRow(
                event    = event,
                fmt      = fmt,
                isFirst  = index == 0,
                isLast   = index == events.lastIndex,
            )
        }
    }
}

@Composable
private fun TimelineRow(event: IncidentEventEntry, fmt: SimpleDateFormat, isFirst: Boolean, isLast: Boolean) {
    Row(verticalAlignment = Alignment.Top) {
        // Bullet column with vertical connector
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(
                imageVector        = Icons.Default.CheckCircle,
                contentDescription = null,
                tint               = MaterialTheme.colorScheme.primary,
                modifier           = Modifier.size(16.dp).clip(CircleShape),
            )
            if (!isLast) {
                Box(
                    modifier = Modifier
                        .width(2.dp)
                        .height(28.dp)
                        .background(MaterialTheme.colorScheme.outline.copy(alpha = 0.4f)),
                )
            }
        }

        Spacer(Modifier.size(AmanahSpacing.sm))

        Column(modifier = Modifier.padding(bottom = AmanahSpacing.sm)) {
            Text(event.label, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
            Text(
                text  = fmt.format(Date(event.timestamp)),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

// ── helpers ────────────────────────────────────────────────────────────────────

private fun formatAbsolute(ts: Long): String =
    SimpleDateFormat("dd MMM yyyy, HH:mm", Locale.getDefault()).format(Date(ts))
