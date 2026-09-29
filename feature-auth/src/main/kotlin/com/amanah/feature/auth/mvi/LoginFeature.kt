package com.amanah.feature.auth.mvi

import com.amanah.feature.auth.model.AuthResult
import com.amanah.feature.auth.model.AuthenticatedUser
import com.amanah.feature.auth.model.FailureReason
import com.amanah.feature.auth.model.UserRole
import com.badoo.mvicore.element.Actor
import com.badoo.mvicore.element.Bootstrapper
import com.badoo.mvicore.element.NewsPublisher
import com.badoo.mvicore.element.Reducer
import com.badoo.mvicore.feature.BaseFeature
import io.reactivex.Observable

// ── State ──────────────────────────────────────────────────────────────────────

data class LoginState(
    val screen: Screen = Screen.Idle,
    val email: String = "",
    val password: String = "",
    val emailError: String? = null,
    val passwordError: String? = null,
    val isPasswordVisible: Boolean = false,
) {
    sealed class Screen {
        object Idle           : Screen()
        object Loading        : Screen()
        object PendingApproval : Screen()
        object Suspended      : Screen()
        data class Error(val message: String) : Screen()
    }

    val isFormValid: Boolean
        get() = email.isNotBlank() && password.length >= 8
}

// ── Wish ───────────────────────────────────────────────────────────────────────

sealed class LoginWish {
    data class EmailChanged(val value: String)    : LoginWish()
    data class PasswordChanged(val value: String) : LoginWish()
    object TogglePasswordVisibility               : LoginWish()
    object Submit                                 : LoginWish()
    object ForgotPassword                         : LoginWish()
    object DismissError                           : LoginWish()
}

// ── Effect ─────────────────────────────────────────────────────────────────────

sealed class LoginEffect {
    data class EmailUpdated(val value: String)       : LoginEffect()
    data class PasswordUpdated(val value: String)    : LoginEffect()
    object PasswordVisibilityToggled                 : LoginEffect()
    object LoginStarted                              : LoginEffect()
    data class LoginSucceeded(val user: AuthenticatedUser) : LoginEffect()
    data class LoginFailed(val reason: FailureReason)      : LoginEffect()
    object PendingApproval                           : LoginEffect()
    object AccountSuspended                          : LoginEffect()
    object ErrorDismissed                            : LoginEffect()
}

// ── News ───────────────────────────────────────────────────────────────────────

sealed class LoginNews {
    data class AuthenticatedAsAdmin(val user: AuthenticatedUser) : LoginNews()
    data class AuthenticatedAsUser(val user: AuthenticatedUser)  : LoginNews()
    object NavigateToForgotPassword                              : LoginNews()
}

// ── Actor ──────────────────────────────────────────────────────────────────────

private class LoginActor(
    private val authenticate: (email: String, password: String) -> Observable<AuthResult>,
) : Actor<LoginState, LoginWish, LoginEffect> {

    override fun invoke(state: LoginState, wish: LoginWish): Observable<out LoginEffect> =
        when (wish) {
            is LoginWish.EmailChanged    -> Observable.just(LoginEffect.EmailUpdated(wish.value))
            is LoginWish.PasswordChanged -> Observable.just(LoginEffect.PasswordUpdated(wish.value))
            LoginWish.TogglePasswordVisibility -> Observable.just(LoginEffect.PasswordVisibilityToggled)
            LoginWish.DismissError       -> Observable.just(LoginEffect.ErrorDismissed)
            LoginWish.ForgotPassword     -> Observable.empty() // handled via News
            LoginWish.Submit -> {
                if (!state.isFormValid) Observable.empty()
                else performLogin(state.email, state.password)
            }
        }

    private fun performLogin(email: String, password: String): Observable<LoginEffect> =
        Observable.create { emitter ->
            emitter.onNext(LoginEffect.LoginStarted)
            authenticate(email, password).subscribe(
                { result ->
                    when (result) {
                        is AuthResult.Success ->
                            emitter.onNext(LoginEffect.LoginSucceeded(result.user))
                        is AuthResult.Failure ->
                            emitter.onNext(LoginEffect.LoginFailed(result.reason))
                        AuthResult.PendingAdminApproval ->
                            emitter.onNext(LoginEffect.PendingApproval)
                        AuthResult.Suspended ->
                            emitter.onNext(LoginEffect.AccountSuspended)
                    }
                },
                { emitter.onNext(LoginEffect.LoginFailed(FailureReason.NETWORK_ERROR)) },
                { emitter.onComplete() },
            )
        }
}

// ── Reducer ────────────────────────────────────────────────────────────────────

private class LoginReducer : Reducer<LoginState, LoginEffect> {
    override fun invoke(state: LoginState, effect: LoginEffect): LoginState = when (effect) {
        is LoginEffect.EmailUpdated           -> state.copy(email = effect.value, emailError = null)
        is LoginEffect.PasswordUpdated        -> state.copy(password = effect.value, passwordError = null)
        LoginEffect.PasswordVisibilityToggled -> state.copy(isPasswordVisible = !state.isPasswordVisible)
        LoginEffect.LoginStarted              -> state.copy(screen = LoginState.Screen.Loading)
        is LoginEffect.LoginSucceeded         -> state // navigation handled via News
        is LoginEffect.LoginFailed            -> state.copy(
            screen = LoginState.Screen.Error(effect.reason.toMessage())
        )
        LoginEffect.PendingApproval           -> state.copy(screen = LoginState.Screen.PendingApproval)
        LoginEffect.AccountSuspended          -> state.copy(screen = LoginState.Screen.Suspended)
        LoginEffect.ErrorDismissed            -> state.copy(screen = LoginState.Screen.Idle)
    }

    private fun FailureReason.toMessage() = when (this) {
        FailureReason.INVALID_CREDENTIALS -> "Invalid email or password."
        FailureReason.NETWORK_ERROR        -> "Network error. Please try again."
        FailureReason.ACCOUNT_NOT_FOUND    -> "No account found. Contact your administrator."
        FailureReason.UNKNOWN              -> "An unexpected error occurred."
    }
}

// ── NewsPublisher ──────────────────────────────────────────────────────────────

private class LoginNewsPublisher :
    NewsPublisher<LoginWish, LoginEffect, LoginState, LoginNews> {
    override fun invoke(wish: LoginWish, effect: LoginEffect, state: LoginState): LoginNews? =
        when {
            effect is LoginEffect.LoginSucceeded && effect.user.role == UserRole.ADMIN ->
                LoginNews.AuthenticatedAsAdmin(effect.user)
            effect is LoginEffect.LoginSucceeded ->
                LoginNews.AuthenticatedAsUser(effect.user)
            wish == LoginWish.ForgotPassword ->
                LoginNews.NavigateToForgotPassword
            else -> null
        }
}

// ── Feature ────────────────────────────────────────────────────────────────────

class LoginFeature(
    authenticate: (email: String, password: String) -> Observable<AuthResult> = { _, _ ->
        // Stub — replace with real repository call
        Observable.just(AuthResult.Failure(FailureReason.UNKNOWN))
    },
) : BaseFeature<LoginWish, LoginWish, LoginEffect, LoginState, LoginNews>(
    initialState  = LoginState(),
    wishToAction  = { it },
    actor         = LoginActor(authenticate),
    reducer       = LoginReducer(),
    newsPublisher = LoginNewsPublisher(),
)
