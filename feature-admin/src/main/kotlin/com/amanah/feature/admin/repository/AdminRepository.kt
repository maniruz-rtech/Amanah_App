package com.amanah.feature.admin.repository

import com.amanah.feature.core.network.ApiService
import com.amanah.feature.core.network.ApprovalDto
import com.amanah.feature.core.network.AuditLogDto
import com.amanah.feature.core.network.IncidentDto
import com.amanah.feature.core.network.PaginatedResponse
import com.amanah.feature.core.network.ResolveRequest
import com.amanah.feature.core.network.SuspendRequest
import com.amanah.feature.core.network.UserProfileDto
import com.amanah.feature.core.repository.Outcome
import com.amanah.feature.core.repository.apiCall

class AdminRepository(
    private val api: ApiService,
) {
    suspend fun listUsers(skip: Int = 0, limit: Int = 50): Outcome<PaginatedResponse<UserProfileDto>> =
        apiCall { api.adminListUsers(skip, limit) }

    suspend fun getUser(userId: String): Outcome<UserProfileDto> =
        apiCall { api.adminGetUser(userId) }

    suspend fun approveUser(userId: String): Outcome<Unit> =
        apiCall { api.adminApproveUser(userId) }

    suspend fun suspendUser(userId: String, reason: String): Outcome<Unit> =
        apiCall { api.adminSuspendUser(userId, SuspendRequest(reason)) }

    suspend fun getIncident(incidentId: String): Outcome<IncidentDto> =
        apiCall { api.getIncident(incidentId) }

    suspend fun resolveIncident(incidentId: String, note: String? = null): Outcome<IncidentDto> =
        apiCall { api.resolveIncident(incidentId, ResolveRequest(note)) }

    suspend fun listAuditLogs(skip: Int = 0, limit: Int = 100): Outcome<PaginatedResponse<AuditLogDto>> =
        apiCall { api.adminListAuditLogs(skip, limit) }

    suspend fun listApprovals(skip: Int = 0, limit: Int = 100): Outcome<PaginatedResponse<ApprovalDto>> =
        apiCall { api.adminListApprovals(skip, limit) }
}
