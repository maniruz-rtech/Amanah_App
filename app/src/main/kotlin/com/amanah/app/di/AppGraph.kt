package com.amanah.app.di

import android.content.Context
import com.amanah.feature.admin.repository.AdminRepository
import com.amanah.feature.auth.repository.AuthRepository
import com.amanah.feature.auth.repository.OtpRepository
import com.amanah.feature.core.network.ApiFactory
import com.amanah.feature.core.network.ApiService
import com.amanah.feature.emergency.repository.EmergencyRepository
import com.amanah.feature.user.repository.DeviceRepository
import com.amanah.feature.user.repository.NotificationsRepository
import com.amanah.feature.user.repository.TrustedContactsRepository
import com.amanah.feature.user.repository.UserRepository
import com.amanah.feature.core.location.FusedLocationProvider
import com.amanah.feature.core.location.LocationProvider
import com.amanah.feature.core.realtime.AppForegroundObserver
import com.amanah.feature.core.realtime.DurableOutboundQueue
import com.amanah.feature.core.realtime.OkHttpRealtimeGateway
import com.amanah.feature.core.realtime.OutboundQueue
import com.amanah.feature.core.realtime.RealtimeGateway
import com.amanah.feature.core.realtime.TokenProvider
import com.amanah.feature.core.session.AppKeysetManager
import com.amanah.feature.core.session.DeviceIdentity
import com.amanah.feature.core.session.SharedPreferencesDeviceIdStore
import com.amanah.feature.core.session.SecureTokenStore
import com.amanah.feature.core.session.SessionManager
import com.amanah.feature.core.session.TinkTokenStore
import com.amanah.feature.core.ui.GlobalSnackbarBus
import com.badoo.reaktive.observable.subscribe
import com.google.gson.Gson
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Manual dependency-injection container.
 *
 * Chosen over Dagger for two reasons:
 *   1. Dagger annotation processing under Bazel/`kt_android_library` requires
 *      additional KAPT-equivalent rule wiring that the project doesn't have
 *      yet — keeping DI manual unblocks the demo without that yak-shave.
 *   2. The graph is small (≈12 nodes); manual wiring is more readable than
 *      generated code at this size.
 *
 * Lifetime: a single instance is created in [AmanahApplication.onCreate] and
 * lives for the process. Everything inside is conceptually a singleton.
 */
class AppGraph(
    private val appContext: Context,
    private val debugBuild: Boolean,
) {
    /** Process-lifetime scope for fire-and-forget work (FCM token registration). */
    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    // ── Configuration ─────────────────────────────────────────────────────────

    /** HTTPS base URL (must be HTTPS in release). */
    val apiBaseUrl: String = DEFAULT_API_BASE_URL

    /** WebSocket URL — wss:// in release, ws:// permitted only in debug builds. */
    val wsUrl: String = DEFAULT_WS_URL

    // ── Persistent storage (Tink + DataStore) ─────────────────────────────────

    val keysetManager: AppKeysetManager by lazy { AppKeysetManager(appContext) }

    val tokenStore: SecureTokenStore by lazy {
        TinkTokenStore(appContext = appContext, keysetManager = keysetManager)
    }

    // ── Device identity (stable per installation, survives sign-out) ──────────

    val deviceIdentity: DeviceIdentity by lazy {
        DeviceIdentity(SharedPreferencesDeviceIdStore(appContext))
    }

    /** `versionName` of the running build, sent to the backend as `app_version`. */
    val appVersion: String? by lazy {
        runCatching { appContext.packageManager.getPackageInfo(appContext.packageName, 0).versionName }
            .getOrNull()
    }

    // ── Session ───────────────────────────────────────────────────────────────

    val sessionManager: SessionManager by lazy { SessionManager(tokenStore) }

    // ── Snackbar bus ──────────────────────────────────────────────────────────

    val snackbarBus: GlobalSnackbarBus by lazy { GlobalSnackbarBus() }

    // ── Shared JSON ───────────────────────────────────────────────────────────

    val gson: Gson by lazy { Gson() }

    // ── Networking (Retrofit + OkHttp, certificate-pinned) ───────────────────

    val apiService: ApiService by lazy {
        ApiFactory.create(
            baseUrl          = apiBaseUrl,
            tokenStore       = tokenStore,
            debug            = debugBuild,
            onSessionExpired = ::onSessionExpired,
        )
    }

    // ── Repositories ──────────────────────────────────────────────────────────

    val authRepository: AuthRepository by lazy {
        AuthRepository(
            api            = apiService,
            sessionManager = sessionManager,
            deviceIdentity = deviceIdentity,
            appVersion     = appVersion,
        )
    }

    // ── Location ──────────────────────────────────────────────────────────────

    /**
     * Process-singleton FusedLocationProviderClient wrapper.
     *
     * Caller starts the appropriate [TrackingProfile] via
     * [LocationProvider.start]. The interactor that owns the dashboard kicks
     * off [TrackingProfile.ACTIVE] on attach and switches to EMERGENCY for
     * the duration of an active incident.
     */
    val locationProvider: LocationProvider by lazy {
        FusedLocationProvider(appContext = appContext)
    }

    // ── FCM bus wiring ────────────────────────────────────────────────────────

    /**
     * Hook FCM signals into the rest of the app.
     *
     *   - token refresh   → DeviceRepository.register(uuid, fcmToken)
     *   - silent wakeup   → realtimeGateway.connect()  (no-op if already online)
     *
     * Incoming-alert routing into the user dashboard is wired by the
     * [RootNode] when the dashboard is attached — the graph doesn't depend
     * on transient UI state.
     */
    fun startPushIntegration() {
        com.amanah.feature.core.push.PushBus.tokens.subscribe { token ->
            appScope.launch {
                deviceRepository.register(
                    deviceUuid = deviceIdentity.deviceUuid,
                    pushToken  = token,
                    appVersion = appVersion,
                )
            }
        }
        com.amanah.feature.core.push.PushBus.wakeups.subscribe {
            realtimeGateway.connect()
        }
    }

    val otpRepository: OtpRepository                       by lazy { OtpRepository(apiService) }
    val userRepository: UserRepository                     by lazy { UserRepository(apiService) }
    val notificationsRepository: NotificationsRepository   by lazy { NotificationsRepository(apiService) }
    val trustedContactsRepository: TrustedContactsRepository by lazy { TrustedContactsRepository(apiService) }
    val deviceRepository: DeviceRepository                 by lazy { DeviceRepository(apiService) }
    val emergencyRepository: EmergencyRepository           by lazy { EmergencyRepository(apiService) }
    val responderRepository: com.amanah.feature.emergency.repository.ResponderRepository
        by lazy { com.amanah.feature.emergency.repository.ResponderRepository(apiService) }
    val adminRepository: AdminRepository                   by lazy { AdminRepository(apiService) }

    // ── Realtime gateway (OkHttp-backed, header auth, pinned) ────────────────

    /**
     * Process-singleton [RealtimeGateway].
     *
     * Token is read at handshake time from the [SecureTokenStore], so a token
     * refresh in the background is picked up on the next reconnect without
     * any reference to the singleton being rebuilt.
     *
     * The gateway is NOT auto-connected. The composition root calls
     * [RealtimeGateway.connect] after sign-in and [RealtimeGateway.disconnect]
     * on logout.
     */
    /** Durable outbound queue — survives process death and reboot. */
    val outboundQueue: OutboundQueue by lazy {
        DurableOutboundQueue(appContext = appContext, gson = gson)
    }

    val realtimeGateway: RealtimeGateway by lazy {
        OkHttpRealtimeGateway(
            httpClient        = ApiFactory.buildWsClient(debug = debugBuild),
            wsBaseUrl         = wsUrl,
            tokenProvider     = TokenProvider { tokenStore.accessToken() },
            gson              = gson,
            outboundQueue     = outboundQueue,
            // WS 401 → exercise the REST refresh interceptor by issuing a no-op
            // `/users/me` call. If that succeeds, the refresh interceptor has
            // already rotated the token and tokenStore.accessToken() now
            // returns the fresh value. We return true so the gateway re-opens.
            // If it fails, we surrender; SessionManager will route to login.
            onAuthRetry      = ::refreshSessionForWebSocket,
            logger            = { msg ->
                if (debugBuild) android.util.Log.d("RealtimeGateway", msg)
            },
        )
    }

    private fun refreshSessionForWebSocket(): Boolean {
        // Run the refresh on a worker thread; the gateway calls us from its
        // single-threaded executor. We use runBlocking deliberately — the
        // gateway expects a synchronous yes/no.
        return try {
            kotlinx.coroutines.runBlocking {
                val outcome = userRepository.me()
                outcome is com.amanah.feature.core.repository.Outcome.Success
            }
        } catch (_: Throwable) {
            false
        }
    }

    /** Bridges [androidx.lifecycle.ProcessLifecycleOwner] into [realtimeGateway]. */
    val foregroundObserver: AppForegroundObserver by lazy {
        AppForegroundObserver(realtimeGateway)
    }

    // ── Internals ─────────────────────────────────────────────────────────────

    private fun onSessionExpired() {
        sessionManager.signOut()
        realtimeGateway.disconnect()
    }

    companion object {
        /**
         * Default base URL for the Android emulator. Replace at build time via
         * `BuildConfig` or by editing this constant.
         *
         * - Android Emulator (cold-host): "http://10.0.2.2:8000"     (debug only)
         * - Physical device on same wifi: "http://<your-laptop-ip>:8000"
         * - Production:                   "https://api.amanah.example"
         */
        const val DEFAULT_API_BASE_URL = "http://10.0.2.2:8000"

        /**
         * Default WS URL. **Always wss:// in release.** Pinned in production
         * (see [com.amanah.feature.core.network.PinningConfig]).
         */
        const val DEFAULT_WS_URL       = "ws://10.0.2.2:8000/ws"
    }
}
