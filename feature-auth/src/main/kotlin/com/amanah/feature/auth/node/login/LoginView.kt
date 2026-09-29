package com.amanah.feature.auth.node.login

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import com.amanah.feature.auth.mvi.LoginState
import com.amanah.feature.auth.mvi.LoginWish
import com.amanah.feature.core.theme.AmanahTheme
import com.amanah.feature.core.ui.AmanahCard
import com.amanah.feature.core.ui.AmanahElevation
import com.amanah.feature.core.ui.AmanahPrimaryButton
import com.amanah.feature.core.ui.AmanahSpacing
import com.amanah.feature.core.ui.AmanahTextField
import com.amanah.lib.nodes.NodeView

// ── Alias so the interactor can use the standard event naming ─────────────────
typealias LoginEvent = LoginWish

class LoginView : NodeView<LoginState, LoginEvent> {

    override var events: ((LoginEvent) -> Unit)? = null

    private var _state by mutableStateOf(LoginState())

    override fun render(state: LoginState) { _state = state }

    @Composable
    fun Content() {
        AmanahTheme {
            LoginScreen(state = _state, onEvent = { events?.invoke(it) })
        }
    }
}

// ── Screen ─────────────────────────────────────────────────────────────────────

@Composable
private fun LoginScreen(state: LoginState, onEvent: (LoginEvent) -> Unit) {
    val snackbarState = remember { SnackbarHostState() }
    val focusManager  = LocalFocusManager.current

    LaunchedEffect(state.screen) {
        if (state.screen is LoginState.Screen.Error) {
            snackbarState.showSnackbar((state.screen as LoginState.Screen.Error).message)
            onEvent(LoginWish.DismissError)
        }
    }

    Scaffold(
        snackbarHost   = { SnackbarHost(snackbarState) },
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .imePadding(),
            contentAlignment = Alignment.Center,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth(0.9f)
                    .verticalScroll(rememberScrollState()),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(AmanahSpacing.sm),
            ) {
                // ── Brand header ───────────────────────────────────────────────
                Text(
                    text  = "Amanah",
                    style = MaterialTheme.typography.displaySmall.copy(fontWeight = FontWeight.Bold),
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    text  = "Community Safety — Member Login",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                Spacer(Modifier.height(AmanahSpacing.lg))

                // ── Form card ─────────────────────────────────────────────────
                AmanahCard(contentPadding = AmanahSpacing.lg) {
                    Column(verticalArrangement = Arrangement.spacedBy(AmanahSpacing.md)) {

                        AmanahTextField(
                            value           = state.email,
                            onValueChange   = { onEvent(LoginWish.EmailChanged(it)) },
                            label           = "Email",
                            leadingIcon     = Icons.Default.Email,
                            keyboardType    = KeyboardType.Email,
                            imeAction       = ImeAction.Next,
                            keyboardActions = KeyboardActions(onNext = { focusManager.moveFocus(FocusDirection.Down) }),
                            errorText       = state.emailError,
                        )

                        AmanahTextField(
                            value           = state.password,
                            onValueChange   = { onEvent(LoginWish.PasswordChanged(it)) },
                            label           = "Password",
                            leadingIcon     = Icons.Default.Lock,
                            isPassword      = true,
                            passwordVisible = state.isPasswordVisible,
                            keyboardType    = KeyboardType.Password,
                            imeAction       = ImeAction.Done,
                            keyboardActions = KeyboardActions(onDone = {
                                focusManager.clearFocus()
                                onEvent(LoginWish.Submit)
                            }),
                            errorText       = state.passwordError,
                            trailingContent = {
                                IconButton(onClick = { onEvent(LoginWish.TogglePasswordVisibility) }) {
                                    Icon(
                                        imageVector = if (state.isPasswordVisible) Icons.Default.VisibilityOff
                                                       else Icons.Default.Visibility,
                                        contentDescription = if (state.isPasswordVisible) "Hide password" else "Show password",
                                    )
                                }
                            },
                        )

                        AmanahPrimaryButton(
                            text    = "Sign In",
                            onClick = { onEvent(LoginWish.Submit) },
                            enabled = state.isFormValid,
                            loading = state.screen is LoginState.Screen.Loading,
                        )

                        TextButton(
                            onClick  = { onEvent(LoginWish.ForgotPassword) },
                            modifier = Modifier.align(Alignment.CenterHorizontally),
                        ) {
                            Text("Forgot password? Contact admin")
                        }
                    }
                }

                // ── Info banners ───────────────────────────────────────────────
                AnimatedVisibility(
                    visible = state.screen is LoginState.Screen.PendingApproval,
                    enter   = fadeIn(),
                    exit    = fadeOut(),
                ) {
                    InfoBanner(
                        text  = "Your account is awaiting admin approval. You'll be notified via email.",
                        color = MaterialTheme.colorScheme.secondaryContainer,
                    )
                }

                AnimatedVisibility(
                    visible = state.screen is LoginState.Screen.Suspended,
                    enter   = fadeIn(),
                    exit    = fadeOut(),
                ) {
                    InfoBanner(
                        text  = "Your account has been suspended. Contact your administrator.",
                        color = MaterialTheme.colorScheme.errorContainer,
                    )
                }

                Spacer(Modifier.height(AmanahSpacing.md))

                Text(
                    text  = "Accounts are created by administrators only.",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.outline,
                )
            }
        }
    }
}

@Composable
private fun InfoBanner(text: String, color: androidx.compose.ui.graphics.Color) {
    AmanahCard(containerColor = color, elevation = AmanahElevation.none) {
        Text(
            text  = text,
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
