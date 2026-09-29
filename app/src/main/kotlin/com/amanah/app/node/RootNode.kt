package com.amanah.app.node

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.amanah.app.di.AppGraph
import com.amanah.feature.admin.node.alertdetail.AdminAlertDetailNode
import com.amanah.feature.admin.node.alertdetail.AdminAlertDetailView
import com.amanah.feature.admin.node.dashboard.AdminDashboardNode
import com.amanah.feature.admin.node.dashboard.AdminDashboardView
import com.amanah.feature.admin.node.userdetail.AdminUserDetailNode
import com.amanah.feature.admin.node.userdetail.AdminUserDetailView
import com.amanah.feature.auth.model.AuthenticatedUser
import com.amanah.feature.auth.node.login.LoginNode
import com.amanah.feature.auth.node.login.LoginView
import com.amanah.feature.auth.node.onboarding.OnboardingNode
import com.amanah.feature.auth.node.onboarding.OnboardingView
import com.amanah.feature.auth.node.passwordreset.PasswordResetNode
import com.amanah.feature.auth.node.passwordreset.PasswordResetView
import com.amanah.feature.core.node.splash.SplashNode
import com.amanah.feature.core.node.splash.SplashView
import com.amanah.feature.user.node.dashboard.UserDashboardNode
import com.amanah.feature.user.node.dashboard.UserDashboardView
import com.amanah.feature.user.node.incidentdetail.IncidentDetailNode
import com.amanah.feature.user.node.incidentdetail.IncidentDetailView
import com.amanah.lib.nodes.NodeContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Root of the Amanah Node tree.
 *
 * Navigation contract:
 *
 *   SPLASH
 *     └─(first-launch)──► ONBOARDING ──► LOGIN
 *     └─(returning)─────► LOGIN
 *           ├─(role=ADMIN)──► ADMIN_DASHBOARD ──► ADMIN_ALERT_DETAIL
 *           │                                   ──► ADMIN_USER_DETAIL
 *           ├─(role=USER )──► USER_DASHBOARD  ──► INCIDENT_DETAIL
 *           └─(forgot pw)──► PASSWORD_RESET   ──► LOGIN
 *
 * Invariants:
 *   - Exactly ONE child node is active (attached) at any time.
 *   - Role gating is performed exclusively in [LoginNode]'s router.
 *   - The active session lives in [AppGraph.sessionManager]; this node merely
 *     mirrors its current state into the navigation stack.
 */
class RootNode(
    private val nodeContext: NodeContext,
    private val graph: AppGraph,
) {

    // ── Navigation state ───────────────────────────────────────────────────────

    private sealed class Screen {
        object Splash         : Screen()
        object Onboarding     : Screen()
        object Login          : Screen()
        object PasswordReset  : Screen()
        data class AdminDash(val user: AuthenticatedUser)        : Screen()
        data class AdminAlertDetail(val alertId: String, val user: AuthenticatedUser) : Screen()
        data class AdminUserDetail(val userId: String,  val user: AuthenticatedUser)  : Screen()
        data class UserDash(val user: AuthenticatedUser)         : Screen()
        data class IncidentDetail(val alertId: String, val user: AuthenticatedUser)   : Screen()
    }

    private var _screen by mutableStateOf<Screen>(Screen.Splash)
    private var onboardingShown: Boolean = false   // session-scope; persist in TokenStore later

    private val rehydrationScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    // ── Lazily constructed child nodes ─────────────────────────────────────────

    private val splashNode: SplashNode by lazy {
        SplashNode(nodeContext = nodeContext.child(), onNavigateToDashboard = ::onSplashFinished)
    }

    private val onboardingNode: OnboardingNode by lazy {
        OnboardingNode(nodeContext = nodeContext.child(), onCompleted = ::showLogin)
    }

    private val loginNode: LoginNode by lazy {
        LoginNode(
            nodeContext              = nodeContext.child(),
            onAdminAuthenticated     = ::showAdminDashboard,
            onUserAuthenticated      = ::showUserDashboard,
            onPasswordResetRequested = ::showPasswordReset,
            authRepository           = graph.authRepository,
        )
    }

    private val passwordResetNode: PasswordResetNode by lazy {
        PasswordResetNode(nodeContext = nodeContext.child(), onBack = ::showLogin)
    }

    private var adminDashboardNode: AdminDashboardNode? = null
    private var userDashboardNode:  UserDashboardNode?  = null
    private var adminAlertDetailNode: AdminAlertDetailNode? = null
    private var adminUserDetailNode:  AdminUserDetailNode?  = null
    private var incidentDetailNode:   IncidentDetailNode?   = null

    // ── Lifecycle ──────────────────────────────────────────────────────────────

    fun onAttach() {
        splashNode.performAttach()
    }

    fun onDetach() {
        detachActive()
    }

    private fun detachActive() {
        when (val screen = _screen) {
            Screen.Splash        -> splashNode.performDetach()
            Screen.Onboarding    -> onboardingNode.performDetach()
            Screen.Login         -> loginNode.performDetach()
            Screen.PasswordReset -> passwordResetNode.performDetach()
            is Screen.AdminDash         -> adminDashboardNode?.performDetach()
            is Screen.AdminAlertDetail  -> adminAlertDetailNode?.performDetach()
            is Screen.AdminUserDetail   -> adminUserDetailNode?.performDetach()
            is Screen.UserDash          -> userDashboardNode?.performDetach()
            is Screen.IncidentDetail    -> incidentDetailNode?.performDetach()
        }
    }

    // ── Routing helpers ────────────────────────────────────────────────────────

    private fun onSplashFinished() {
        splashNode.performDetach()

        // Returning user with a persisted session → skip the login funnel and
        // hydrate from /users/me directly. Tokens live in the Tink store; if
        // they're rejected (refresh failed), the refresh interceptor signals
        // SessionExpired which clears the store and we fall through to login.
        if (graph.tokenStore.hasSession()) {
            tryRehydrateSession()
            return
        }

        if (!onboardingShown) {
            onboardingNode.performAttach()
            _screen = Screen.Onboarding
        } else {
            showLogin()
        }
    }

    /**
     * Fetch the current user via [UserRepository.me], then route into
     * Admin/User dashboard. Falls back to login if the call fails.
     *
     * Note: the splash node is already detached. We leave the screen in
     * Splash state visually while the network call resolves — this is the
     * same gating logic the app uses on a fresh login, so it's already a
     * known-fast path.
     */
    private fun tryRehydrateSession() {
        rehydrationScope.launch {
            val outcome = graph.userRepository.me()
            withContext(Dispatchers.Main) {
                when (outcome) {
                    is com.amanah.feature.core.repository.Outcome.Success -> {
                        val dto  = outcome.value
                        val role = if (dto.roles.any { it in ADMIN_ROLE_NAMES })
                            com.amanah.feature.auth.model.UserRole.ADMIN
                        else
                            com.amanah.feature.auth.model.UserRole.USER

                        val token = graph.tokenStore.accessToken()
                        if (token == null) {
                            showLogin()
                            return@withContext
                        }
                        val user = AuthenticatedUser(
                            userId       = dto.id,
                            displayName  = dto.displayName ?: dto.username,
                            email        = dto.email ?: "",
                            phone        = dto.phone ?: "",
                            role         = role,
                            status       = com.amanah.feature.auth.model.AccountStatus.ACTIVE,
                            sessionToken = token,
                        )

                        if (role == com.amanah.feature.auth.model.UserRole.ADMIN) {
                            showAdminDashboard(user)
                        } else {
                            showUserDashboard(user)
                        }
                    }
                    else -> {
                        graph.tokenStore.clear()
                        showLogin()
                    }
                }
            }
        }
    }

    private companion object {
        val ADMIN_ROLE_NAMES = setOf("super_admin", "regional_admin", "admin", "ADMIN")
    }

    private fun showLogin() {
        when (val screen = _screen) {
            Screen.Onboarding    -> {
                onboardingShown = true
                onboardingNode.performDetach()
            }
            Screen.PasswordReset -> passwordResetNode.performDetach()
            is Screen.UserDash   -> userDashboardNode?.performDetach()
            is Screen.AdminDash  -> adminDashboardNode?.performDetach()
            else                 -> Unit
        }
        loginNode.performAttach()
        _screen = Screen.Login
    }

    private fun showPasswordReset() {
        loginNode.performDetach()
        passwordResetNode.performAttach()
        _screen = Screen.PasswordReset
    }

    private fun showAdminDashboard(user: AuthenticatedUser) {
        loginNode.performDetach()
        adminDashboardNode = AdminDashboardNode(
            nodeContext  = nodeContext.child(),
            admin        = user,
            onEditUser   = { userId -> openAdminUserDetail(userId, user) },
            onShowToast  = { msg -> graph.snackbarBus.post(msg) },
            repository   = graph.adminRepository,
        ).also { it.performAttach() }
        _screen = Screen.AdminDash(user)
    }

    private fun openAdminUserDetail(userId: String, admin: AuthenticatedUser) {
        adminDashboardNode?.performDetach()
        adminUserDetailNode = AdminUserDetailNode(
            nodeContext   = nodeContext.child(),
            userId        = userId,
            onBack        = { closeAdminUserDetail(admin) },
            onUserUpdated = { _ -> graph.snackbarBus.post("User updated.") },
            repository    = graph.adminRepository,
        ).also { it.performAttach() }
        _screen = Screen.AdminUserDetail(userId, admin)
    }

    private fun closeAdminUserDetail(admin: AuthenticatedUser) {
        adminUserDetailNode?.performDetach()
        adminUserDetailNode = null
        showAdminDashboard(admin)
    }

    fun openAdminAlertDetail(alertId: String) {
        val admin = (_screen as? Screen.AdminDash)?.user ?: return
        adminDashboardNode?.performDetach()
        adminAlertDetailNode = AdminAlertDetailNode(
            nodeContext = nodeContext.child(),
            alertId     = alertId,
            onBack      = { closeAdminAlertDetail(admin) },
            onResolved  = { _ -> graph.snackbarBus.post("Alert resolved.") },
            repository  = graph.adminRepository,
        ).also { it.performAttach() }
        _screen = Screen.AdminAlertDetail(alertId, admin)
    }

    private fun closeAdminAlertDetail(admin: AuthenticatedUser) {
        adminAlertDetailNode?.performDetach()
        adminAlertDetailNode = null
        showAdminDashboard(admin)
    }

    private fun showUserDashboard(user: AuthenticatedUser) {
        loginNode.performDetach()
        // Connect the realtime gateway exactly once per session — reading the
        // current token from SecureTokenStore at handshake time.
        graph.realtimeGateway.connect()
        userDashboardNode = UserDashboardNode(
            nodeContext          = nodeContext.child(),
            authenticatedUser    = user,
            onEmergencyTriggered = { /* EmergencyAlertEngine handles outbound */ },
            onIncomingEmergency  = { alertId, lat, lng ->
                userDashboardNode?.interactor?.onIncomingAlert(alertId, lat, lng)
            },
            onLogout            = ::onLogout,
            realtimeGateway     = graph.realtimeGateway,
            emergencyRepository = graph.emergencyRepository,
            userRepository      = graph.userRepository,
            locationProvider    = graph.locationProvider,
        ).also { it.performAttach() }
        _screen = Screen.UserDash(user)
    }

    fun openIncidentDetail(alertId: String) {
        val user = (_screen as? Screen.UserDash)?.user ?: return
        userDashboardNode?.performDetach()
        incidentDetailNode = IncidentDetailNode(
            nodeContext    = nodeContext.child(),
            alertId        = alertId,
            onBack         = { closeIncidentDetail(user) },
            userRepository = graph.userRepository,
        ).also { it.performAttach() }
        _screen = Screen.IncidentDetail(alertId, user)
    }

    private fun closeIncidentDetail(user: AuthenticatedUser) {
        incidentDetailNode?.performDetach()
        incidentDetailNode = null
        showUserDashboard(user)
    }

    private fun onLogout() {
        userDashboardNode?.performDetach()
        userDashboardNode = null
        graph.realtimeGateway.disconnect()
        graph.sessionManager.signOut()
        showLogin()
    }

    // ── Compose entry point ────────────────────────────────────────────────────

    @Composable
    fun Content() {
        when (val screen = _screen) {
            Screen.Splash        -> (splashNode.view as? SplashView)?.Content()
            Screen.Onboarding    -> (onboardingNode.view as? OnboardingView)?.Content()
            Screen.Login         -> (loginNode.view as? LoginView)?.Content()
            Screen.PasswordReset -> (passwordResetNode.view as? PasswordResetView)?.Content()
            is Screen.AdminDash         -> (adminDashboardNode?.view as? AdminDashboardView)?.Content()
            is Screen.AdminAlertDetail  -> (adminAlertDetailNode?.view as? AdminAlertDetailView)?.Content()
            is Screen.AdminUserDetail   -> (adminUserDetailNode?.view as? AdminUserDetailView)?.Content()
            is Screen.UserDash          -> (userDashboardNode?.view as? UserDashboardView)?.Content()
            is Screen.IncidentDetail    -> (incidentDetailNode?.view as? IncidentDetailView)?.Content()
        }
    }
}
