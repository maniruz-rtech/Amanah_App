package com.amanah.feature.auth.model

sealed class AuthResult {
    data class Success(val user: AuthenticatedUser) : AuthResult()
    data class Failure(val reason: FailureReason)   : AuthResult()
    object PendingAdminApproval                     : AuthResult()
    object Suspended                                : AuthResult()
}

enum class FailureReason {
    INVALID_CREDENTIALS,
    NETWORK_ERROR,
    ACCOUNT_NOT_FOUND,  // accounts are admin-created; no self-registration
    UNKNOWN,
}
