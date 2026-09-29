package com.amanah.feature.core.session

/**
 * Abstract contract for the token store.
 *
 * Exposed as an interface so we can:
 *   - Swap implementations (Tink-backed, in-memory test double, debug fake).
 *   - Keep [com.amanah.feature.core.realtime.RealtimeGateway] and
 *     [com.amanah.feature.core.network.AuthInterceptor] decoupled from the
 *     storage mechanism.
 *
 * All methods are synchronous and non-blocking on a hot path — implementations
 * are expected to cache the access token in memory for synchronous access by
 * OkHttp interceptors. Writes may block briefly on encryption.
 */
interface SecureTokenStore {

    /** Persist a new session. Overwrites any existing tokens. */
    fun save(accessToken: String, refreshToken: String)

    /** Forget the persisted session. Idempotent. */
    fun clear()

    /** Returns the access token or null if no session exists. Hot path. */
    fun accessToken(): String?

    /** Returns the refresh token or null. Used only by the refresh interceptor. */
    fun refreshToken(): String?

    /** Convenience predicate. */
    fun hasSession(): Boolean = accessToken() != null
}
