package com.amanah.feature.emergency.repository

import com.amanah.feature.core.network.ApiService
import com.amanah.feature.core.network.AvailabilityDto
import com.amanah.feature.core.network.AvailabilityUpdateRequest
import com.amanah.feature.core.network.IncidentDto
import com.amanah.feature.core.network.ResponderAcceptRequest
import com.amanah.feature.core.network.ResponderDeclineRequest
import com.amanah.feature.core.network.ResponderEnRouteRequest
import com.amanah.feature.core.repository.Outcome
import com.amanah.feature.core.repository.apiCall

/**
 * Responder-side coordination flow.
 *
 * State transitions (server-side state machine):
 *
 *   BROADCASTING ──[responder.accept]──► ACCEPTED
 *   ACCEPTED     ──[responder.en-route]─► EN_ROUTE
 *   EN_ROUTE     ──[responder.arrived]──► ARRIVED
 *   ARRIVED      ──[server resolve]─────► RESOLVED
 *
 *   BROADCASTING / ACCEPTED ──[responder.decline]──► (assignment marked
 *                                                     declined; incident
 *                                                     may stay open for
 *                                                     another responder)
 *
 * Every transition is persisted in `incident_events` and `audit_logs` by
 * the backend service layer.
 */
class ResponderRepository(
    private val api: ApiService,
) {

    suspend fun getAvailability(): Outcome<AvailabilityDto> =
        apiCall { api.getResponderAvailability() }

    suspend fun setAvailability(
        isAvailable: Boolean,
        lat: Double? = null,
        lng: Double? = null,
        batteryLevel: Int? = null,
    ): Outcome<AvailabilityDto> = apiCall {
        api.setResponderAvailability(
            AvailabilityUpdateRequest(isAvailable, lat, lng, batteryLevel)
        )
    }

    suspend fun accept(incidentId: String, etaMinutes: Int): Outcome<IncidentDto> = apiCall {
        api.responderAccept(incidentId, ResponderAcceptRequest(etaMinutes))
    }

    suspend fun decline(incidentId: String, reason: String): Outcome<IncidentDto> = apiCall {
        api.responderDecline(incidentId, ResponderDeclineRequest(reason))
    }

    suspend fun enRoute(
        incidentId: String,
        lat: Double,
        lng: Double,
        etaSeconds: Int? = null,
    ): Outcome<IncidentDto> = apiCall {
        api.responderEnRoute(incidentId, ResponderEnRouteRequest(lat, lng, etaSeconds))
    }

    suspend fun arrived(incidentId: String): Outcome<IncidentDto> = apiCall {
        api.responderArrived(incidentId)
    }
}
