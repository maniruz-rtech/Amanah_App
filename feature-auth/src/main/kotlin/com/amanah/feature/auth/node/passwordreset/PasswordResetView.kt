package com.amanah.feature.auth.node.passwordreset

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.amanah.feature.core.theme.AmanahTheme
import com.amanah.lib.nodes.NodeView

data class PasswordResetState(
    val contactValue: String = "",
    val isSubmitted: Boolean = false,
)

sealed class PasswordResetEvent {
    data class ContactChanged(val value: String) : PasswordResetEvent()
    object Submit                                : PasswordResetEvent()
    object Back                                  : PasswordResetEvent()
}

class PasswordResetView : NodeView<PasswordResetState, PasswordResetEvent> {

    override var events: ((PasswordResetEvent) -> Unit)? = null

    private var _state by mutableStateOf(PasswordResetState())

    override fun render(state: PasswordResetState) { _state = state }

    @Composable
    fun Content() {
        AmanahTheme {
            PasswordResetScreen(state = _state, onEvent = { events?.invoke(it) })
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PasswordResetScreen(state: PasswordResetState, onEvent: (PasswordResetEvent) -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Password Reset") },
                navigationIcon = {
                    IconButton(onClick = { onEvent(PasswordResetEvent.Back) }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            if (state.isSubmitted) {
                // ── Confirmation state ─────────────────────────────────────────
                Card(
                    colors   = CardDefaults.cardColors(MaterialTheme.colorScheme.secondaryContainer),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            "Request Submitted",
                            style = MaterialTheme.typography.titleMedium,
                        )
                        Text(
                            "An admin has been notified. Once approved, you'll receive a reset " +
                            "link via your registered phone or email. This process is admin-controlled " +
                            "and may take up to 24 hours.",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            } else {
                // ── Input state ────────────────────────────────────────────────
                Text(
                    "Admin-Approved Reset",
                    style = MaterialTheme.typography.headlineSmall,
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    "Because accounts are admin-controlled, password resets must be " +
                    "approved by your administrator. Enter your registered email or phone.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(24.dp))

                OutlinedTextField(
                    value       = state.contactValue,
                    onValueChange = { onEvent(PasswordResetEvent.ContactChanged(it)) },
                    label       = { Text("Email or Phone Number") },
                    singleLine  = true,
                    modifier    = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(16.dp))

                Button(
                    onClick  = { onEvent(PasswordResetEvent.Submit) },
                    enabled  = state.contactValue.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Request Admin Reset")
                }
            }
        }
    }
}
