package com.amanah.feature.admin.model

import com.amanah.feature.auth.model.AccountStatus
import com.amanah.feature.auth.model.UserRole

data class UserRecord(
    val userId: String,
    val displayName: String,
    val email: String,
    val phone: String,
    val role: UserRole,
    val status: AccountStatus,
    val createdAt: Long,
    val lastSeenAt: Long? = null,
    val h3Cell: String? = null,         // last known H3 cell at resolution 7
    val alertsTriggered: Int = 0,
)
