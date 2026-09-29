package com.amanah.feature.user.repository

import com.amanah.feature.core.network.ApiService
import com.amanah.feature.core.network.IncidentDto
import com.amanah.feature.core.network.NearbyUsersDto
import com.amanah.feature.core.network.PresencePingPayload
import com.amanah.feature.core.network.UpdateProfileRequest
import com.amanah.feature.core.network.UserProfileDto
import com.amanah.feature.core.repository.Outcome
import com.amanah.feature.core.repository.apiCall

/**
 * Real backend-backed user data.
 *
 * Methods return [Outcome] — callers never need to handle exceptions.
 */
class UserRepository(
    private val api: ApiService,
) {

    suspend fun me(): Outcome<UserProfileDto> = apiCall { api.me() }

    suspend fun updateMe(
        displayName: String? = null,
        email: String? = null,
        phone: String? = null,
    ): Outcome<UserProfileDto> = apiCall {
        api.updateMe(UpdateProfileRequest(displayName, email, phone))
    }

    /** History of the user's own incidents (active first). */
    suspend fun listMyActiveIncidents(): Outcome<List<IncidentDto>> = apiCall {
        api.myActiveIncidents()
    }

    suspend fun getIncident(incidentId: String): Outcome<IncidentDto> = apiCall {
        api.getIncident(incidentId)
    }

    /**
     * Periodic presence ping. The client supplies its H3 cells; the backend
     * persists them + bumps `last_seen_at`. Cheap, idempotent — call every
     * 60s while the dashboard is in foreground.
     */
    suspend fun pingPresence(
        h3CellDistrict: String,
        h3CellBlock: String? = null,
    ): Outcome<Unit> = apiCall {
        api.pingPresence(PresencePingPayload(h3CellDistrict, h3CellBlock))
    }

    /**
     * Returns members in the supplied H3 cells (typically a k-ring around
     * the caller's own cell). The client computes the k-ring locally via
     * [com.amanah.lib.location.H3LocationIndex.nearbyAddresses].
     */
    suspend fun listNearby(
        cells: List<String>,
        maxIdleSeconds: Int = 600,
        limit: Int = 50,
    ): Outcome<NearbyUsersDto> = apiCall {
        api.listNearby(
            cells          = cells.joinToString(","),
            maxIdleSeconds = maxIdleSeconds,
            limit          = limit,
        )
    }
}
