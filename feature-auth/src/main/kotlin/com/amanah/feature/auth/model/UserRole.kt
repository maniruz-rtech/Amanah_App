package com.amanah.feature.auth.model

enum class UserRole { ADMIN, USER }

enum class AccountStatus {
    ACTIVE,           // can log in
    PENDING_APPROVAL, // admin has not yet approved the account
    SUSPENDED,        // admin revoked access
}

data class AuthenticatedUser(
    val userId: String,
    val displayName: String,
    val email: String,
    val phone: String,
    val role: UserRole,
    val status: AccountStatus,
    val sessionToken: String,
)
