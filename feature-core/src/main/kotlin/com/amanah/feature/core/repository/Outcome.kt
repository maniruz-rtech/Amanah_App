package com.amanah.feature.core.repository

import retrofit2.HttpException

/**
 * Discriminated result type for every repository call.
 *
 * Standard `kotlin.Result` is intentionally rejected — it swallows the error
 * category. For an emergency app the call-site needs to differentiate
 * recoverable network / server errors from non-recoverable authentication
 * failures.
 *
 * Repositories MUST NOT throw. Every public method returns [Outcome].
 *
 * Pattern:
 *   when (val r = userRepo.me()) {
 *       is Outcome.Success     -> render(r.value)
 *       is Outcome.NetworkDown -> showOffline()
 *       is Outcome.AuthFailed  -> kickToLogin()
 *       is Outcome.ServerError -> showError(r.code, r.message)
 *       is Outcome.Unexpected  -> showError(null, "Unexpected")
 *   }
 */
sealed class Outcome<out T> {
    data class Success<T>(val value: T) : Outcome<T>()

    /** No connectivity, DNS failure, or socket reset. Retryable. */
    object NetworkDown : Outcome<Nothing>()

    /** Backend returned 401 / 403 — token invalid or session revoked. Not retryable; reroute to login. */
    object AuthFailed : Outcome<Nothing>()

    /** Backend returned 4xx (validation) or 5xx (internal). */
    data class ServerError(val code: Int, val message: String?) : Outcome<Nothing>()

    /** Catch-all for non-HTTP exceptions (serialization, illegal state). Reported to Sentry. */
    data class Unexpected(val cause: Throwable) : Outcome<Nothing>()

    inline fun <R> map(transform: (T) -> R): Outcome<R> = when (this) {
        is Success      -> Success(transform(value))
        NetworkDown     -> NetworkDown
        AuthFailed      -> AuthFailed
        is ServerError  -> this
        is Unexpected   -> this
    }

    fun successOr(default: @UnsafeVariance T): T = if (this is Success) value else default
    fun successOrNull(): T?      = (this as? Success)?.value
}

/**
 * Wrap a Retrofit suspend call into an [Outcome]. Maps exceptions to the
 * narrowest meaningful category.
 */
suspend inline fun <T> apiCall(crossinline block: suspend () -> T): Outcome<T> {
    return try {
        Outcome.Success(block())
    } catch (e: HttpException) {
        when (e.code()) {
            401, 403 -> Outcome.AuthFailed
            else     -> Outcome.ServerError(e.code(), e.message())
        }
    } catch (e: java.io.IOException) {
        Outcome.NetworkDown
    } catch (e: Throwable) {
        Outcome.Unexpected(e)
    }
}
