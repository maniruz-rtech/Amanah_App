package com.amanah.feature.admin.node.dashboard

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.NotificationImportant
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.amanah.feature.admin.model.AlertHistoryEntry
import com.amanah.feature.admin.model.AlertStatus
import com.amanah.feature.admin.model.UserRecord
import com.amanah.feature.admin.mvi.AdminState
import com.amanah.feature.admin.mvi.AdminWish
import com.amanah.feature.auth.model.AccountStatus
import com.amanah.feature.core.theme.AmanahTheme
import com.amanah.lib.nodes.NodeView
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// ── Event alias ────────────────────────────────────────────────────────────────
typealias AdminEvent = AdminWish

// ── NodeView implementation ────────────────────────────────────────────────────

class AdminDashboardView : NodeView<AdminState, AdminEvent> {

    override var events: ((AdminEvent) -> Unit)? = null

    private var _state by mutableStateOf(AdminState())

    override fun render(state: AdminState) { _state = state }

    @Composable
    fun Content() {
        AmanahTheme {
            AdminDashboardScreen(state = _state, onEvent = { events?.invoke(it) })
        }
    }
}

// ── Root scaffold ──────────────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AdminDashboardScreen(state: AdminState, onEvent: (AdminEvent) -> Unit) {
    val snackbar = remember { SnackbarHostState() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Admin Command Center", style = MaterialTheme.typography.titleLarge)
                        Text("Amanah Safety", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant,
                ),
                actions = {
                    if (state.activeAlertCount > 0) {
                        BadgedBox(badge = {
                            Badge { Text(state.activeAlertCount.toString()) }
                        }) {
                            Icon(Icons.Default.NotificationImportant, "Active alerts",
                                tint = MaterialTheme.colorScheme.error)
                        }
                    }
                },
            )
        },
        bottomBar = {
            AdminBottomNav(selected = state.tab, onSelect = { onEvent(AdminWish.SelectTab(it)) },
                pendingCount = state.pendingApprovalCount)
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        if (state.isLoading) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            return@Scaffold
        }

        AnimatedContent(
            targetState = state.tab,
            transitionSpec = { fadeIn().togetherWith(fadeOut()) },
            modifier = Modifier.fillMaxSize().padding(padding),
            label = "AdminTabContent",
        ) { tab ->
            when (tab) {
                AdminState.Tab.USERS  -> UsersTab(state, onEvent)
                AdminState.Tab.ALERTS -> AlertsTab(state, onEvent)
                AdminState.Tab.STATS  -> StatsTab(state)
            }
        }
    }
}

// ── Bottom nav ─────────────────────────────────────────────────────────────────

@Composable
private fun AdminBottomNav(
    selected: AdminState.Tab,
    onSelect: (AdminState.Tab) -> Unit,
    pendingCount: Int,
) {
    NavigationBar {
        NavigationBarItem(
            selected = selected == AdminState.Tab.USERS,
            onClick  = { onSelect(AdminState.Tab.USERS) },
            icon     = {
                BadgedBox(badge = {
                    if (pendingCount > 0) Badge { Text(pendingCount.toString()) }
                }) {
                    Icon(Icons.Default.People, "Users")
                }
            },
            label = { Text("Users") },
        )
        NavigationBarItem(
            selected = selected == AdminState.Tab.ALERTS,
            onClick  = { onSelect(AdminState.Tab.ALERTS) },
            icon     = { Icon(Icons.Default.History, "Alerts") },
            label    = { Text("Alert Log") },
        )
        NavigationBarItem(
            selected = selected == AdminState.Tab.STATS,
            onClick  = { onSelect(AdminState.Tab.STATS) },
            icon     = { Icon(Icons.Default.Warning, "Stats") },
            label    = { Text("Stats") },
        )
    }
}

// ── Users tab ──────────────────────────────────────────────────────────────────

@Composable
private fun UsersTab(state: AdminState, onEvent: (AdminEvent) -> Unit) {
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {

        OutlinedTextField(
            value = state.searchQuery,
            onValueChange = { onEvent(AdminWish.SearchChanged(it)) },
            placeholder = { Text("Search users…") },
            singleLine  = true,
            modifier    = Modifier.fillMaxWidth(),
        )

        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(state.filteredUsers, key = { it.userId }) { user ->
                UserCard(user = user, onEvent = onEvent)
            }
        }
    }
}

@Composable
private fun UserCard(user: UserRecord, onEvent: (AdminEvent) -> Unit) {
    val statusColor = when (user.status) {
        AccountStatus.ACTIVE           -> MaterialTheme.colorScheme.primary
        AccountStatus.PENDING_APPROVAL -> MaterialTheme.colorScheme.secondary
        AccountStatus.SUSPENDED        -> MaterialTheme.colorScheme.error
    }

    Card(
        modifier  = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(1.dp),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Status indicator bar
            Box(
                modifier = Modifier
                    .size(width = 4.dp, height = 56.dp)
                    .background(statusColor, MaterialTheme.shapes.small)
            )

            Column(
                modifier = Modifier.weight(1f).padding(start = 12.dp),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Text(user.displayName, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Text(user.email, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(
                    text = user.status.name.replace('_', ' '),
                    style = MaterialTheme.typography.labelSmall,
                    color = statusColor,
                    fontWeight = FontWeight.Medium,
                )
            }

            // Action buttons
            if (user.status == AccountStatus.PENDING_APPROVAL) {
                IconButton(onClick = { onEvent(AdminWish.ApproveUser(user.userId)) }) {
                    Icon(Icons.Default.CheckCircle, "Approve", tint = MaterialTheme.colorScheme.primary)
                }
            }
            IconButton(onClick = { onEvent(AdminWish.EditUser(user.userId)) }) {
                Icon(Icons.Default.Edit, "Edit")
            }
            if (user.status != AccountStatus.SUSPENDED) {
                IconButton(onClick = { onEvent(AdminWish.SuspendUser(user.userId)) }) {
                    Icon(Icons.Default.Delete, "Suspend", tint = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}

// ── Alerts tab ─────────────────────────────────────────────────────────────────

@Composable
private fun AlertsTab(state: AdminState, onEvent: (AdminEvent) -> Unit) {
    val fmt = remember { SimpleDateFormat("dd MMM HH:mm", Locale.getDefault()) }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(state.alerts, key = { it.alertId }) { alert ->
            AlertCard(alert = alert, fmt = fmt, onEvent = onEvent)
        }
    }
}

@Composable
private fun AlertCard(alert: AlertHistoryEntry, fmt: SimpleDateFormat, onEvent: (AdminEvent) -> Unit) {
    val isActive = alert.status == AlertStatus.ACTIVE
    val borderColor = if (isActive) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.outline

    Card(
        modifier  = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(if (isActive) 4.dp else 1.dp),
        colors    = CardDefaults.cardColors(
            containerColor = if (isActive) MaterialTheme.colorScheme.errorContainer
                             else MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text(
                    text  = "Alert #${alert.alertId.takeLast(6).uppercase()}",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text  = alert.status.name,
                    style = MaterialTheme.typography.labelSmall,
                    color = if (isActive) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.outline,
                    fontWeight = FontWeight.SemiBold,
                )
            }
            Text("Triggered by: ${alert.triggeredByName}", style = MaterialTheme.typography.bodySmall)
            Text("H3 Cell: ${alert.h3Cell}", style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("Notified: ${alert.respondersNotified}   Acknowledged: ${alert.respondersAcknowledged}",
                style = MaterialTheme.typography.bodySmall)
            Text(fmt.format(Date(alert.triggeredAt)), style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)

            if (isActive) {
                Spacer(Modifier.height(8.dp))
                Button(
                    onClick = { onEvent(AdminWish.ResolveAlert(alert.alertId)) },
                    colors  = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Force Resolve") }
            }
        }
    }
}

// ── Stats tab ──────────────────────────────────────────────────────────────────

@Composable
private fun StatsTab(state: AdminState) {
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("Total Users",    state.users.size.toString(), MaterialTheme.colorScheme.primaryContainer)
        StatCard("Active Users",   state.users.count { it.status == AccountStatus.ACTIVE }.toString(), MaterialTheme.colorScheme.secondaryContainer)
        StatCard("Pending Approval", state.pendingApprovalCount.toString(), MaterialTheme.colorScheme.tertiaryContainer)
        StatCard("Total Alerts",   state.alerts.size.toString(), MaterialTheme.colorScheme.errorContainer)
        StatCard("Active Alerts",  state.activeAlertCount.toString(), MaterialTheme.colorScheme.errorContainer)
    }
}

@Composable
private fun StatCard(label: String, value: String, color: Color) {
    Card(
        colors   = CardDefaults.cardColors(containerColor = color),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Text(label, style = MaterialTheme.typography.bodyMedium)
            Text(value, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        }
    }
}
