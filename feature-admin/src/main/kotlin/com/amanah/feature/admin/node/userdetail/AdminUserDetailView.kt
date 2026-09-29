package com.amanah.feature.admin.node.userdetail

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
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.PhoneAndroid
import androidx.compose.material3.Divider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import com.amanah.feature.auth.model.AccountStatus
import com.amanah.feature.auth.model.UserRole
import com.amanah.feature.core.theme.AmanahTheme
import com.amanah.feature.core.ui.AmanahCard
import com.amanah.feature.core.ui.AmanahDestructiveButton
import com.amanah.feature.core.ui.AmanahLoadingState
import com.amanah.feature.core.ui.AmanahPrimaryButton
import com.amanah.feature.core.ui.AmanahScaffold
import com.amanah.feature.core.ui.AmanahSecondaryButton
import com.amanah.feature.core.ui.AmanahSpacing
import com.amanah.feature.core.ui.AmanahStatusBadge
import com.amanah.feature.core.ui.AmanahTopBar
import com.amanah.feature.core.ui.BadgeTone
import com.amanah.lib.nodes.NodeView
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ── Contract ───────────────────────────────────────────────────────────────────

data class DeviceEntry(
    val deviceId: String,
    val name: String,
    val osVersion: String,
    val lastSeen: Long,
)

data class ActivityEntry(
    val id: String,
    val label: String,
    val timestamp: Long,
)

data class AdminUserDetailState(
    val userId: String,
    val isLoading: Boolean = true,
    val isMutating: Boolean = false,
    val displayName: String? = null,
    val email: String? = null,
    val phone: String? = null,
    val role: UserRole? = null,
    val status: AccountStatus? = null,
    val createdAt: Long = 0L,
    val lastLoginAt: Long? = null,
    val devices: List<DeviceEntry> = emptyList(),
    val recentActivity: List<ActivityEntry> = emptyList(),
)

sealed class AdminUserDetailEvent {
    object Back                                       : AdminUserDetailEvent()
    object Approve                                    : AdminUserDetailEvent()
    object Suspend                                    : AdminUserDetailEvent()
    object ResetPassword                              : AdminUserDetailEvent()
    data class RevokeDevice(val deviceId: String)     : AdminUserDetailEvent()
}

// ── NodeView ───────────────────────────────────────────────────────────────────

class AdminUserDetailView : NodeView<AdminUserDetailState, AdminUserDetailEvent> {
    override var events: ((AdminUserDetailEvent) -> Unit)? = null
    private var _state by mutableStateOf<AdminUserDetailState?>(null)
    override fun render(state: AdminUserDetailState) { _state = state }

    @Composable
    fun Content() {
        AmanahTheme {
            val state = _state
            if (state == null) {
                AmanahLoadingState(message = "Loading user…")
                return@AmanahTheme
            }
            AdminUserDetailScreen(state = state, onEvent = { events?.invoke(it) })
        }
    }
}

// ── Screen ─────────────────────────────────────────────────────────────────────

@Composable
private fun AdminUserDetailScreen(state: AdminUserDetailState, onEvent: (AdminUserDetailEvent) -> Unit) {
    AmanahScaffold(
        topBar = {
            AmanahTopBar(
                title    = state.displayName ?: "User",
                subtitle = state.role?.name?.replace('_', ' '),
                onBack   = { onEvent(AdminUserDetailEvent.Back) },
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
                .padding(padding)
                .padding(horizontal = AmanahSpacing.md, vertical = AmanahSpacing.md)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(AmanahSpacing.md),
        ) {
            IdentityCard(state)
            ContactCard(state)
            ActionRow(state, onEvent)
            DevicesCard(state, onEvent)
            ActivityCard(state)
        }
    }
}

// ── Sections ───────────────────────────────────────────────────────────────────

@Composable
private fun IdentityCard(state: AdminUserDetailState) {
    AmanahCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                imageVector        = Icons.Default.AccountCircle,
                contentDescription = null,
                tint               = MaterialTheme.colorScheme.primary,
                modifier           = Modifier
                    .size(56.dp)
                    .clip(CircleShape),
            )
            Spacer(Modifier.size(AmanahSpacing.md))
            Column(modifier = Modifier.weight(1f)) {
                Text(state.displayName ?: "—", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Text("ID: ${state.userId.takeLast(8)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            AmanahStatusBadge(
                text = state.status?.name?.replace('_', ' ') ?: "—",
                tone = when (state.status) {
                    AccountStatus.ACTIVE           -> BadgeTone.POSITIVE
                    AccountStatus.PENDING_APPROVAL -> BadgeTone.WARNING
                    AccountStatus.SUSPENDED        -> BadgeTone.CRITICAL
                    null                            -> BadgeTone.NEUTRAL
                },
            )
        }
    }
}

@Composable
private fun ContactCard(state: AdminUserDetailState) {
    AmanahCard {
        Text("Contact", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(AmanahSpacing.sm))
        Row {
            Text("Email", modifier = Modifier.weight(1f), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(state.email ?: "—", style = MaterialTheme.typography.bodyMedium)
        }
        Spacer(Modifier.height(AmanahSpacing.xs))
        Row {
            Text("Phone", modifier = Modifier.weight(1f), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(state.phone ?: "—", style = MaterialTheme.typography.bodyMedium)
        }
        Spacer(Modifier.height(AmanahSpacing.xs))
        Row {
            Text("Joined", modifier = Modifier.weight(1f), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(formatDate(state.createdAt), style = MaterialTheme.typography.bodyMedium)
        }
        Spacer(Modifier.height(AmanahSpacing.xs))
        Row {
            Text("Last login", modifier = Modifier.weight(1f), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(state.lastLoginAt?.let(::formatDate) ?: "Never", style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun ActionRow(state: AdminUserDetailState, onEvent: (AdminUserDetailEvent) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(AmanahSpacing.sm)) {
        when (state.status) {
            AccountStatus.PENDING_APPROVAL ->
                AmanahPrimaryButton(text = "Approve account", onClick = { onEvent(AdminUserDetailEvent.Approve) }, loading = state.isMutating)
            AccountStatus.ACTIVE ->
                AmanahDestructiveButton(text = "Suspend account", onClick = { onEvent(AdminUserDetailEvent.Suspend) }, loading = state.isMutating)
            AccountStatus.SUSPENDED ->
                AmanahPrimaryButton(text = "Reactivate", onClick = { onEvent(AdminUserDetailEvent.Approve) }, loading = state.isMutating)
            null -> Unit
        }
        AmanahSecondaryButton(text = "Trigger password reset", onClick = { onEvent(AdminUserDetailEvent.ResetPassword) })
    }
}

@Composable
private fun DevicesCard(state: AdminUserDetailState, onEvent: (AdminUserDetailEvent) -> Unit) {
    AmanahCard {
        Text("Devices", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(AmanahSpacing.sm))
        if (state.devices.isEmpty()) {
            Text("No devices registered.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        state.devices.forEachIndexed { index, device ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.PhoneAndroid, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.size(AmanahSpacing.sm))
                Column(modifier = Modifier.weight(1f)) {
                    Text(device.name, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
                    Text("${device.osVersion} · last seen ${formatDate(device.lastSeen)}",
                        style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                TextButton(onClick = { onEvent(AdminUserDetailEvent.RevokeDevice(device.deviceId)) }) {
                    Text("Revoke", color = MaterialTheme.colorScheme.error)
                }
            }
            if (index < state.devices.lastIndex) Divider(modifier = Modifier.padding(vertical = AmanahSpacing.xs))
        }
    }
}

@Composable
private fun ActivityCard(state: AdminUserDetailState) {
    val fmt = remember { SimpleDateFormat("dd MMM HH:mm", Locale.getDefault()) }
    AmanahCard {
        Text("Recent activity", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(AmanahSpacing.sm))
        if (state.recentActivity.isEmpty()) {
            Text("No recent activity.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        state.recentActivity.forEachIndexed { index, entry ->
            Row {
                Text(fmt.format(Date(entry.timestamp)),
                    modifier = Modifier.weight(0.4f),
                    style    = MaterialTheme.typography.labelSmall,
                    color    = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(entry.label, modifier = Modifier.weight(0.6f),
                    style    = MaterialTheme.typography.bodySmall)
            }
            if (index < state.recentActivity.lastIndex) Spacer(Modifier.height(AmanahSpacing.xs))
        }
    }
}

private fun formatDate(ts: Long): String =
    SimpleDateFormat("dd MMM yyyy, HH:mm", Locale.getDefault()).format(Date(ts))
