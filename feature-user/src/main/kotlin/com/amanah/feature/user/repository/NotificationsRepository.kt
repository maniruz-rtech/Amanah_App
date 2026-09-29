package com.amanah.feature.user.repository

import com.amanah.feature.core.network.ApiService
import com.amanah.feature.core.network.MarkReadRequest
import com.amanah.feature.core.network.NotificationDto
import com.amanah.feature.core.network.PaginatedResponse
import com.amanah.feature.core.repository.Outcome
import com.amanah.feature.core.repository.apiCall

class NotificationsRepository(
    private val api: ApiService,
) {
    suspend fun list(skip: Int = 0, limit: Int = 50): Outcome<PaginatedResponse<NotificationDto>> =
        apiCall { api.listNotifications(skip, limit) }

    suspend fun markRead(ids: List<String>): Outcome<Unit> =
        apiCall { api.markRead(MarkReadRequest(ids)) }

    suspend fun markAllRead(): Outcome<Unit> =
        apiCall { api.markAllRead() }

    suspend fun unreadCount(): Outcome<Int> =
        apiCall { api.unreadCount().count }
}
