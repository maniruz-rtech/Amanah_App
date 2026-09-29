package com.amanah.feature.core.network

import com.amanah.feature.core.session.SecureTokenStore
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Adds `Authorization: Bearer <access_token>` to all non-public requests.
 *
 * The Bearer header is the **only** place tokens may be carried in transit.
 * Query parameters carrying tokens are forbidden — proxies, load balancers,
 * and analytics SDKs frequently log request URLs verbatim.
 *
 * The token value is read from [SecureTokenStore.accessToken] on every request
 * so a freshly rotated token is picked up without rebuilding the client.
 */
class AuthInterceptor(private val tokenStore: SecureTokenStore) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        if (isPublic(request.url.encodedPath)) return chain.proceed(request)

        val token = tokenStore.accessToken() ?: return chain.proceed(request)
        val authed = request.newBuilder()
            .addHeader("Authorization", "Bearer $token")
            .build()
        return chain.proceed(authed)
    }

    private fun isPublic(path: String): Boolean =
        path.endsWith("/auth/login") ||
        path.endsWith("/auth/refresh") ||
        path.endsWith("/auth/password-reset/request") ||
        path.endsWith("/health")
}
