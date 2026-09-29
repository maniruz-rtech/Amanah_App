package com.amanah.feature.core.network

import com.amanah.feature.core.session.SecureTokenStore
import com.google.gson.Gson
import okhttp3.CertificatePinner
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Constructs the singleton [ApiService] and the supporting OkHttp clients.
 *
 * Three OkHttpClients are produced (all sharing the same connection pool):
 *   - [authedClient]   — pinned + interceptor chain (auth + refresh + logging).
 *   - [refreshClient]  — pinned, bare client used only by [RefreshInterceptor]
 *                        for /auth/refresh, to avoid recursion through the
 *                        refresh interceptor itself.
 *   - WS client        — built separately via [buildWsClient]; pinned, no
 *                        interceptors (auth happens at handshake via header).
 *
 * Certificate pinning is mandatory in release builds (see [PinningConfig]).
 * SSL pinning errors fast-fail rather than reconnect-loop.
 */
object ApiFactory {

    fun create(
        baseUrl: String,
        tokenStore: SecureTokenStore,
        debug: Boolean,
        onSessionExpired: () -> Unit,
    ): ApiService {
        val gson    = Gson()
        val pinner  = PinningConfig.forBuild(debugBuild = debug)

        val refreshClient = baseClient(debug, pinner).build()

        val authedClient = baseClient(debug, pinner)
            .addInterceptor(AuthInterceptor(tokenStore))
            .addInterceptor(
                RefreshInterceptor(
                    tokenStore       = tokenStore,
                    baseUrl          = baseUrl.trimEnd('/'),
                    refreshClient    = refreshClient,
                    gson             = gson,
                    onSessionExpired = onSessionExpired,
                )
            )
            .build()

        return Retrofit.Builder()
            .baseUrl(if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/")
            .client(authedClient)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(ApiService::class.java)
    }

    /**
     * Build the OkHttp client used by the realtime gateway.
     *
     * **No interceptors** — WebSocket upgrade requests don't pass through
     * application-level interceptors and the Authorization header is added
     * explicitly when the gateway issues `newWebSocket()`.
     *
     * Pinning IS applied so the WS upgrade is MITM-protected before any frame
     * is exchanged.
     */
    fun buildWsClient(debug: Boolean): OkHttpClient {
        val pinner = PinningConfig.forBuild(debugBuild = debug)
        return OkHttpClient.Builder()
            .certificatePinner(pinner)
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(0,    TimeUnit.MILLISECONDS)   // long-lived stream — disable read timeout
            .writeTimeout(15,  TimeUnit.SECONDS)
            .pingInterval(0,   TimeUnit.SECONDS)        // ping handled by HeartbeatScheduler, not OkHttp
            .retryOnConnectionFailure(false)            // gateway handles reconnect deterministically
            .build()
    }

    private fun baseClient(debug: Boolean, pinner: CertificatePinner): OkHttpClient.Builder {
        val b = OkHttpClient.Builder()
            .certificatePinner(pinner)
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30,    TimeUnit.SECONDS)
            .writeTimeout(30,   TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)

        if (debug) {
            val logging = HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BODY
                // Authorization header value contains the JWT — never log it.
                redactHeader("Authorization")
                redactHeader("Cookie")
            }
            b.addInterceptor(logging)
        }
        return b
    }
}
