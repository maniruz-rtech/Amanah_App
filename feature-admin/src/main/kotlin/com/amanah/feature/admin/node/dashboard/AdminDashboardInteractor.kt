package com.amanah.feature.admin.node.dashboard

import com.amanah.feature.admin.model.AlertHistoryEntry
import com.amanah.feature.admin.model.AlertStatus
import com.amanah.feature.admin.model.UserRecord
import com.amanah.feature.admin.mvi.AdminFeature
import com.amanah.feature.admin.mvi.AdminNews
import com.amanah.feature.admin.mvi.AdminWish
import com.amanah.feature.admin.repository.AdminRepository
import com.amanah.feature.auth.model.AccountStatus
import com.amanah.feature.auth.model.UserRole
import com.amanah.feature.core.network.UserProfileDto
import com.amanah.feature.core.repository.Outcome
import com.amanah.lib.nodes.Interactor
import io.reactivex.Observable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Admin dashboard interactor.
 *
 * - On attach: kicks `LoadAll` (loading state) and then calls
 *   [AdminRepository.listUsers] in parallel with an alerts load. Pushes the
 *   results back into the MVI feature via [AdminWish.UsersLoaded] and
 *   [AdminWish.AlertsLoaded].
 *
 * - On Approve/Suspend wishes: forwards the action to the repository, then
 *   re-fetches the user list to reflect the latest state. Optimistic UI
 *   updates are handled by the MVI reducer.
 */
class AdminDashboardInteractor(
    private val feature: AdminFeature = AdminFeature(),
    private val repository: AdminRepository? = null,
) : Interactor<AdminDashboardView, AdminDashboardRouter>() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onAttach() {
        Observable.wrap(feature).subscribe { state -> view?.render(state) }
            .autoDispose()

        Observable.wrap(feature.news).subscribe { news ->
            when (news) {
                is AdminNews.NavigateToEditUser ->
                    router?.navigateToEditUser(news.userId)
                is AdminNews.ShowToast ->
                    router?.showToast(news.message)
            }
        }.autoDispose()

        view?.events = { wish ->
            feature.accept(wish)
            handleSideEffect(wish)
        }

        // Initial load
        repository?.let { loadAll(it) }
    }

    override fun onDetach() {
        view?.events = null
        feature.dispose()
        scope.cancel()
    }

    /** Called by WebSocket observer in RootNode to inject live alerts. */
    fun onLiveAlertReceived(entry: AlertHistoryEntry) {
        feature.accept(AdminWish.LoadAll)
        repository?.let { loadAll(it) }
    }

    // ── private ────────────────────────────────────────────────────────────────

    private fun handleSideEffect(wish: AdminWish) {
        val repo = repository ?: return
        when (wish) {
            is AdminWish.ApproveUser -> scope.launch {
                if (repo.approveUser(wish.userId) is Outcome.Success) loadAll(repo)
            }
            is AdminWish.SuspendUser -> scope.launch {
                if (repo.suspendUser(wish.userId, "admin_suspended") is Outcome.Success) loadAll(repo)
            }
            is AdminWish.ResolveAlert -> scope.launch {
                if (repo.resolveIncident(wish.alertId, note = "admin_force_resolved") is Outcome.Success) loadAll(repo)
            }
            else -> Unit
        }
    }

    private fun loadAll(repo: AdminRepository) {
        scope.launch {
            when (val outcome = repo.listUsers()) {
                is Outcome.Success -> {
                    val records = outcome.value.items.map { it.toUserRecord() }
                    feature.accept(AdminWish.UsersLoaded(records))
                }
                Outcome.AuthFailed     -> feature.accept(AdminWish.LoadFailed("Session expired"))
                Outcome.NetworkDown    -> feature.accept(AdminWish.LoadFailed("No network"))
                is Outcome.ServerError -> feature.accept(AdminWish.LoadFailed("Server error ${outcome.code}"))
                is Outcome.Unexpected  -> feature.accept(AdminWish.LoadFailed("Unexpected error"))
            }
        }
        scope.launch {
            // No `/admin/incidents` aggregator endpoint yet; alerts list will populate
            // via live WebSocket events. Push an empty list to drop the loading
            // shimmer; this is replaced by [onLiveAlertReceived] as events arrive.
            feature.accept(AdminWish.AlertsLoaded(emptyList()))
        }
    }

    private fun UserProfileDto.toUserRecord(): UserRecord {
        val role = if (roles.any { it in ADMIN_ROLE_NAMES }) UserRole.ADMIN else UserRole.USER
        val status = when {
            isSuspended  -> AccountStatus.SUSPENDED
            !isVerified  -> AccountStatus.PENDING_APPROVAL
            else         -> AccountStatus.ACTIVE
        }
        return UserRecord(
            userId       = id,
            displayName  = displayName ?: username,
            email        = email ?: "",
            phone        = phone ?: "",
            role         = role,
            status       = status,
            createdAt    = System.currentTimeMillis(),
        )
    }

    private companion object {
        val ADMIN_ROLE_NAMES = setOf("super_admin", "regional_admin", "admin", "ADMIN")
    }
}
