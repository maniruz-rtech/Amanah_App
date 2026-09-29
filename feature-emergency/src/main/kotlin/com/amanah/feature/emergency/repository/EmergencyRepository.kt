package com.amanah.feature.emergency.repository

import com.amanah.feature.core.network.ApiService
import com.amanah.feature.core.network.CancelRequest
import com.amanah.feature.core.network.IncidentDto
import com.amanah.feature.core.network.ResolveRequest
import com.amanah.feature.core.network.SosRequest
import com.amanah.feature.core.network.LocationUpdate as ApiLocationUpdate
import com.amanah.feature.core.repository.Outcome
import com.amanah.feature.core.repository.apiCall
import kotlinx.coroutines.delay

/**
 * The canonical persistence path for every incident lifecycle event.
 *
 * Why this exists: the previous design sent emergency alerts only via the
 * WebSocket. The WebSocket handler did not persist. This meant a triggered
 * SOS produced no `incidents` row, no `incident_events` row, and no
 * `audit_logs` row — leaving a safety-critical event with zero forensic
 * trace.
 *
 * This repository makes REST the single source of truth. The WebSocket
 * remains the *delivery channel* (server broadcasts to nearby clients) but
 * never the trigger channel.
 *
 * Retry policy:
 *   - On NetworkDown, we retry with exponential backoff. The user's SOS
 *     must reach the server even on a flaky connection.
 *   - On AuthFailed, we do NOT retry — the user needs to re-authenticate.
 *   - On ServerError 5xx, we retry up to [SOS_RETRY_MAX] times.
 *   - On 4xx other than 401/403, we surface immediately (validation error).
 *
 * Idempotency: the server is expected to dedupe by `event_id` when supplied
 * (server-side improvement tracked separately). For now the client is
 * responsible for not double-submitting (the UI gates on phase != BROADCASTING).
 */
class EmergencyRepository(
    private val api: ApiService,
) {

    /**
     * Trigger an SOS. Persisted via `POST /api/v1/incidents/sos`. The server
     * persists incident + emergency_locations + incident_events + audit_logs
     * and then broadcasts an `emergency.alert` envelope to nearby clients
     * via the realtime channel.
     */
    suspend fun createSos(
        lat: Double,
        lng: Double,
        h3Cell: String? = null,
        accuracyMeters: Int? = null,
        incidentType: String = "SOS",
        severity: String = "HIGH",
        silentMode: Boolean = false,
        note: String? = null,
    ): Outcome<IncidentDto> {
        val request = SosRequest(
            lat            = lat,
            lng            = lng,
            accuracyMeters = accuracyMeters,
            h3Cell         = h3Cell,
            incidentType   = incidentType,
            severity       = severity,
            silentMode     = silentMode,
            note           = note,
        )
        return retryOnTransient(maxAttempts = SOS_RETRY_MAX) {
            apiCall { api.createSos(request) }
        }
    }

    /**
     * Periodic location update while an incident is active. Persisted to
     * `emergency_locations` and broadcast to assigned responders.
     */
    suspend fun pushLocation(
        incidentId: String,
        lat: Double,
        lng: Double,
        accuracyMeters: Int? = null,
    ): Outcome<Unit> = apiCall {
        api.pushLocation(incidentId, ApiLocationUpdate(lat = lat, lng = lng, accuracyMeters = accuracyMeters))
    }

    suspend fun cancel(incidentId: String, reason: String): Outcome<IncidentDto> = apiCall {
        api.cancelIncident(incidentId, CancelRequest(reason))
    }

    suspend fun resolve(incidentId: String, note: String? = null): Outcome<IncidentDto> = apiCall {
        api.resolveIncident(incidentId, ResolveRequest(note))
    }

    suspend fun getIncident(incidentId: String): Outcome<IncidentDto> = apiCall {
        api.getIncident(incidentId)
    }

    suspend fun listMyActive(): Outcome<List<IncidentDto>> = apiCall {
        api.myActiveIncidents()
    }

    // ── private ────────────────────────────────────────────────────────────────

    private suspend inline fun <T> retryOnTransient(
        maxAttempts: Int,
        crossinline block: suspend () -> Outcome<T>,
    ): Outcome<T> {
        var attempt = 0
        var last: Outcome<T>
        while (true) {
            attempt++
            last = block()
            // Stop on terminal outcomes
            when (last) {
                is Outcome.Success     -> return last
                Outcome.AuthFailed     -> return last
                is Outcome.ServerError -> {
                    if (last.code in 500..599 && attempt < maxAttempts) {
                        delay(backoffMs(attempt)); continue
                    }
                    return last
                }
                Outcome.NetworkDown -> {
                    if (attempt < maxAttempts) { delay(backoffMs(attempt)); continue }
                    return last
                }
                is Outcome.Unexpected  -> return last
            }
        }
    }

    private fun backoffMs(attempt: Int): Long =
        // 500 ms, 1s, 2s, 4s — bounded
        (500L * (1L shl (attempt - 1).coerceAtMost(3))).coerceAtMost(4_000L)

    private companion object {
        const val SOS_RETRY_MAX = 4
    }
}
