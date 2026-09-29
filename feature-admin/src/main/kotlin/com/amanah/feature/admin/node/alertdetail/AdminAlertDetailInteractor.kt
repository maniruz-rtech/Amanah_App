package com.amanah.feature.admin.node.alertdetail

import com.amanah.feature.admin.repository.AdminRepository
import com.amanah.feature.core.network.IncidentDto
import com.amanah.feature.core.repository.Outcome
import com.amanah.lib.nodes.Interactor
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class AdminAlertDetailInteractor(
    private val alertId: String,
    private val repository: AdminRepository? = null,
) : Interactor<AdminAlertDetailView, AdminAlertDetailRouter>() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var current = AdminAlertDetailState(alertId = alertId, isLoading = true)

    override fun onAttach() {
        view?.render(current)
        repository?.let { loadAlert(it) }

        view?.events = handler@{ event ->
            when (event) {
                AdminAlertDetailEvent.Back -> router?.onBack()

                AdminAlertDetailEvent.ForceResolve -> {
                    val repo = repository ?: return@handler
                    current = current.copy(isResolving = true)
                    view?.render(current)
                    scope.launch {
                        when (repo.resolveIncident(alertId, note = "admin_force_resolved")) {
                            is Outcome.Success -> {
                                current = current.copy(isResolving = false, status = AlertStatus.RESOLVED)
                                view?.render(current)
                                router?.onResolved(alertId)
                            }
                            else -> {
                                current = current.copy(isResolving = false)
                                view?.render(current)
                            }
                        }
                    }
                }

                AdminAlertDetailEvent.Escalate -> Unit  // surfacing-only; no backend action yet
            }
        }
    }

    override fun onDetach() {
        view?.events = null
        scope.cancel()
    }

    private fun loadAlert(repo: AdminRepository) {
        scope.launch {
            when (val outcome = repo.getIncident(alertId)) {
                is Outcome.Success -> {
                    current = outcome.value.toState()
                    view?.render(current)
                }
                else -> {
                    current = current.copy(isLoading = false)
                    view?.render(current)
                }
            }
        }
    }

    private fun IncidentDto.toState(): AdminAlertDetailState =
        AdminAlertDetailState(
            alertId             = id,
            isLoading           = false,
            status              = parseStatus(status),
            triggeredAt         = System.currentTimeMillis(),  // ts comes in via WS / next iteration
            victimName          = null,                         // joined separately
            victimLat           = null,                         // PostGIS encoded — fetched via separate endpoint
            victimLng           = null,
            h3Cell              = h3Cell,
            responders          = emptyList(),                  // populated via WS in this iteration
            notifiedCount       = 0,
            acknowledgedCount   = 0,
        )

    private fun parseStatus(s: String): AlertStatus = runCatching {
        AlertStatus.valueOf(s.uppercase().replace('-', '_'))
    }.getOrDefault(AlertStatus.ACTIVE)
}
