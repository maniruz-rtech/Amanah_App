package com.amanah.feature.core.network

import com.amanah.feature.core.session.SecureTokenStore
import com.google.gson.Gson
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response

/**
 * Single-flight refresh interceptor.
 *
 * On a 401 response:
 *   1. Acquires a coarse-grained mutex so concurrent failed calls share one
 *      refresh attempt.
 *   2. Calls `/api/v1/auth/refresh` on a separate client without this
 *      interceptor (to prevent recursion).
 *   3. If refresh succeeds, replays the original request **once** with the
 *      new bearer token. If the retry also returns 401, the session is
 *      considered hard-expired and [onSessionExpired] is invoked.
 *   4. If refresh itself fails, the session is cleared and [onSessionExpired]
 *      fires.
 *
 * The refresh request body and any returned tokens are never logged — both
 * `Authorization` and `Cookie` headers are redacted by the HttpLogging
 * interceptor (see [ApiFactory.baseClient]).
 */
class RefreshInterceptor(
    private val tokenStore: SecureTokenStore,
    private val baseUrl: String,
    private val refreshClient: OkHttpClient,
    private val gson: Gson,
    private val onSessionExpired: () -> Unit,
) : Interceptor {

    @Volatile private var inFlight = false
    private val lock = Any()

    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        val response = chain.proceed(original)

        if (response.code != 401) return response

        val refreshed = synchronized(lock) {
            val current = tokenStore.accessToken()
            if (current != null && original.header("Authorization") != "Bearer $current") {
                // Another thread already refreshed; reuse its new token.
                current
            } else if (!inFlight) {
                inFlight = true
                try {
                    refreshTokens()
                } finally {
                    inFlight = false
                }
            } else {
                tokenStore.accessToken()
            }
        }

        if (refreshed == null) {
            tokenStore.clear()
            onSessionExpired()
            return response
        }

        response.close()
        val retried = original.newBuilder()
            .removeHeader("Authorization")
            .addHeader("Authorization", "Bearer $refreshed")
            .build()
        val retryResp = chain.proceed(retried)
        if (retryResp.code == 401) {
            // Hard expired — refresh succeeded but the access token still didn't work.
            tokenStore.clear()
            onSessionExpired()
        }
        return retryResp
    }

    private fun refreshTokens(): String? {
        val refreshToken = tokenStore.refreshToken() ?: return null
        val body = gson.toJson(RefreshRequest(refreshToken))
            .toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("$baseUrl/api/v1/auth/refresh")
            .post(body)
            .build()
        return try {
            refreshClient.newCall(request).execute().use { resp ->
                if (!resp.isSuccessful) return null
                val payload = resp.body?.string() ?: return null
                val tokens = gson.fromJson(payload, TokenResponse::class.java)
                tokenStore.save(tokens.accessToken, tokens.refreshToken)
                tokens.accessToken
            }
        } catch (_: Exception) {
            null
        }
    }
}
