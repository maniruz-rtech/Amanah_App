package com.amanah.feature.auth.repository

import com.amanah.feature.auth.model.AccountStatus
import com.amanah.feature.auth.model.AuthResult
import com.amanah.feature.auth.model.AuthenticatedUser
import com.amanah.feature.auth.model.FailureReason
import com.amanah.feature.auth.model.UserRole
import com.amanah.feature.core.network.ApiService
import com.amanah.feature.core.network.LoginRequest
import com.amanah.feature.core.network.PasswordResetRequest
import com.amanah.feature.core.network.UserProfileDto
import com.amanah.feature.core.session.DeviceIdentity
import com.amanah.feature.core.session.SessionManager
import io.reactivex.Observable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import retrofit2.HttpException

/**
 * Bridges the [ApiService] auth surface to the Reaktive observables consumed
 * by the MVICore `LoginFeature`. Owns the DTO → [AuthenticatedUser] mapping
 * (kept in this module to avoid feature-core ↔ feature-auth cycles).
 */
class AuthRepository(
    private val api: ApiService,
    private val sessionManager: SessionManager,
    private val deviceIdentity: DeviceIdentity,
    private val appVersion: String? = null,
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.IO),
) {

    fun login(email: String, password: String): Observable<AuthResult> = Observable.create { emitter ->
        scope.launch {
            try {
                val response = api.login(
                    LoginRequest(
                        username   = email,
                        password   = password,
                        deviceUuid = deviceIdentity.deviceUuid,
                        appVersion = appVersion,
                    )
                )
                val user = toAuthenticatedUser(response.user, response.accessToken)
                sessionManager.signIn(
                    session      = AuthSession(user),
                    accessToken  = response.accessToken,
                    refreshToken = response.refreshToken,
                )
                emitter.onNext(AuthResult.Success(user))
                emitter.onComplete()
            } catch (e: HttpException) {
                emitter.onNext(mapHttpError(e))
                emitter.onComplete()
            } catch (e: Exception) {
                emitter.onNext(AuthResult.Failure(FailureReason.NETWORK_ERROR))
                emitter.onComplete()
            }
        }
    }

    fun requestPasswordReset(usernameOrEmail: String): Observable<Boolean> = Observable.create { emitter ->
        scope.launch {
            try {
                api.requestPasswordReset(PasswordResetRequest(usernameOrEmail))
                emitter.onNext(true)
                emitter.onComplete()
            } catch (_: Exception) {
                emitter.onNext(false)
                emitter.onComplete()
            }
        }
    }

    // ── helpers ────────────────────────────────────────────────────────────────

    private fun toAuthenticatedUser(dto: UserProfileDto, accessToken: String): AuthenticatedUser =
        AuthenticatedUser(
            userId       = dto.id,
            displayName  = dto.displayName ?: dto.username,
            email        = dto.email ?: "",
            phone        = dto.phone ?: "",
            role         = if (dto.roles.any { it in ADMIN_ROLE_NAMES }) UserRole.ADMIN else UserRole.USER,
            status       = when {
                dto.isSuspended -> AccountStatus.SUSPENDED
                !dto.isVerified -> AccountStatus.PENDING_APPROVAL
                else            -> AccountStatus.ACTIVE
            },
            sessionToken = accessToken,
        )

    private fun mapHttpError(e: HttpException): AuthResult = when (e.code()) {
        401  -> AuthResult.Failure(FailureReason.INVALID_CREDENTIALS)
        403  -> AuthResult.Suspended
        404  -> AuthResult.Failure(FailureReason.ACCOUNT_NOT_FOUND)
        423  -> AuthResult.Suspended
        else -> AuthResult.Failure(FailureReason.UNKNOWN)
    }

    private companion object {
        val ADMIN_ROLE_NAMES = setOf("super_admin", "regional_admin", "ADMIN", "admin")
    }
}

/**
 * Session record materialised from an authenticated user. Implements
 * [SessionManager.Session] so the core module need not know about
 * [AuthenticatedUser].
 */
data class AuthSession(val user: AuthenticatedUser) : SessionManager.Session {
    override val userId: String  = user.userId
    override val isAdmin: Boolean = user.role == UserRole.ADMIN
}
