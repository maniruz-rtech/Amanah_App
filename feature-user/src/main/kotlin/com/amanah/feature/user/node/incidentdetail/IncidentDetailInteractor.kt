package com.amanah.feature.user.node.incidentdetail

import com.amanah.feature.core.network.IncidentDto
import com.amanah.feature.core.repository.Outcome
import com.amanah.feature.user.repository.UserRepository
import com.amanah.lib.nodes.Interactor
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/**
 * Loads incident detail by hitting `GET /api/v1/incidents/{id}` and mapping
 * the response to [IncidentDetailState].
 *
 * If [userRepository] is null (preview mode), an empty state is rendered.
 */
class IncidentDetailInteractor(
    private val alertId: String,
    private val userRepository: UserRepository? = null,
) : Interactor<IncidentDetailView, IncidentDetailRouter>() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onAttach() {
        view?.render(IncidentDetailState(alertId = alertId, isLoading = true))

        val repo = userRepository
        if (repo == null) {
            view?.render(IncidentDetailState(alertId = alertId, isLoading = false))
        } else {
            scope.launch {
                when (val outcome = repo.getIncident(alertId)) {
                    is Outcome.Success     -> view?.render(outcome.value.toState())
                    Outcome.AuthFailed     -> view?.render(IncidentDetailState(alertId = alertId, isLoading = false))
                    Outcome.NetworkDown    -> view?.render(IncidentDetailState(alertId = alertId, isLoading = false))
                    is Outcome.ServerError -> view?.render(IncidentDetailState(alertId = alertId, isLoading = false))
                    is Outcome.Unexpected  -> view?.render(IncidentDetailState(alertId = alertId, isLoading = false))
                }
            }
        }

        view?.events = { event ->
            when (event) {
                IncidentDetailEvent.Back -> router?.onBack()
            }
        }
    }

    override fun onDetach() {
        view?.events = null
        scope.cancel()
    }

    private fun IncidentDto.toState(): IncidentDetailState {
        val triggeredMs = parseIso(startedAt) ?: System.currentTimeMillis()
        val resolvedMs  = resolvedAt?.let { parseIso(it) }

        return IncidentDetailState(
            alertId        = id,
            isLoading      = false,
            status         = parseStatus(status),
            triggeredAt    = triggeredMs,
            resolvedAt     = resolvedMs,
            victimLat      = null,                                 // intentionally hidden in the resolved-view UI
            victimLng      = null,
            h3Cell         = h3Cell,
            respondersNotified     = 0,                            // not yet exposed by the DTO; tracked separately
            respondersAcknowledged = 0,
            resolutionNote = null,
            events         = emptyList(),                          // server-side events endpoint pending
        )
    }

    private fun parseStatus(name: String): IncidentStatus = runCatching {
        IncidentStatus.valueOf(name.uppercase().replace('-', '_'))
    }.getOrDefault(IncidentStatus.RESOLVED)

    private fun parseIso(ts: String?): Long? {
        if (ts.isNullOrBlank()) return null
        return runCatching {
            val fmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US)
                .apply { timeZone = TimeZone.getTimeZone("UTC") }
            val cleaned = ts.substringBefore('.').substringBefore('Z')
            fmt.parse(cleaned)?.time
        }.getOrNull()
    }
}
