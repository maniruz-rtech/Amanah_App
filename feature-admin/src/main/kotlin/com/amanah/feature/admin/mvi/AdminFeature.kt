package com.amanah.feature.admin.mvi

import com.amanah.feature.admin.model.AlertHistoryEntry
import com.amanah.feature.admin.model.AlertStatus
import com.amanah.feature.admin.model.UserRecord
import com.amanah.feature.auth.model.AccountStatus
import com.badoo.mvicore.element.Actor
import com.badoo.mvicore.element.Bootstrapper
import com.badoo.mvicore.element.NewsPublisher
import com.badoo.mvicore.element.Reducer
import com.badoo.mvicore.feature.BaseFeature
import io.reactivex.Observable

// ── State ──────────────────────────────────────────────────────────────────────

data class AdminState(
    val tab: Tab = Tab.USERS,
    val users: List<UserRecord> = emptyList(),
    val alerts: List<AlertHistoryEntry> = emptyList(),
    val isLoading: Boolean = true,
    val error: String? = null,
    val searchQuery: String = "",
    val pendingApprovalCount: Int = 0,
    val activeAlertCount: Int = 0,
) {
    enum class Tab { USERS, ALERTS, STATS }

    val filteredUsers: List<UserRecord>
        get() = if (searchQuery.isBlank()) users
                else users.filter {
                    it.displayName.contains(searchQuery, ignoreCase = true) ||
                    it.email.contains(searchQuery, ignoreCase = true)
                }
}

// ── Wish ───────────────────────────────────────────────────────────────────────

sealed class AdminWish {
    object LoadAll                                                : AdminWish()
    data class UsersLoaded(val users: List<UserRecord>)           : AdminWish()
    data class AlertsLoaded(val alerts: List<AlertHistoryEntry>)  : AdminWish()
    data class LoadFailed(val message: String)                    : AdminWish()
    data class SelectTab(val tab: AdminState.Tab)                 : AdminWish()
    data class SearchChanged(val query: String)                   : AdminWish()
    data class ApproveUser(val userId: String)                    : AdminWish()
    data class SuspendUser(val userId: String)                    : AdminWish()
    data class EditUser(val userId: String)                       : AdminWish()
    data class ResolveAlert(val alertId: String)                  : AdminWish()
}

// ── Effect ─────────────────────────────────────────────────────────────────────

sealed class AdminEffect {
    object LoadingStarted                                     : AdminEffect()
    data class DataLoaded(
        val users: List<UserRecord>,
        val alerts: List<AlertHistoryEntry>,
    ) : AdminEffect()
    data class LoadFailed(val message: String)                : AdminEffect()
    data class TabSelected(val tab: AdminState.Tab)           : AdminEffect()
    data class SearchQueryUpdated(val query: String)          : AdminEffect()
    data class UserStatusUpdated(val userId: String, val status: AccountStatus) : AdminEffect()
    data class AlertStatusUpdated(val alertId: String, val status: AlertStatus) : AdminEffect()
    data class LiveAlertReceived(val entry: AlertHistoryEntry) : AdminEffect()
}

// ── News ───────────────────────────────────────────────────────────────────────

sealed class AdminNews {
    data class NavigateToEditUser(val userId: String) : AdminNews()
    data class ShowToast(val message: String)         : AdminNews()
}

// ── Actor ──────────────────────────────────────────────────────────────────────

private class AdminActor : Actor<AdminState, AdminWish, AdminEffect> {

    override fun invoke(state: AdminState, wish: AdminWish): Observable<out AdminEffect> =
        when (wish) {
            // LoadAll just kicks the loading indicator. The Interactor calls
            // AdminRepository directly (Outcome-based) and feeds results back
            // via [AdminWish.UsersLoaded] / [AdminWish.AlertsLoaded].
            AdminWish.LoadAll -> Observable.just(AdminEffect.LoadingStarted)
            is AdminWish.UsersLoaded  -> Observable.just(AdminEffect.DataLoaded(wish.users, state.alerts))
            is AdminWish.AlertsLoaded -> Observable.just(AdminEffect.DataLoaded(state.users, wish.alerts))
            is AdminWish.LoadFailed   -> Observable.just(AdminEffect.LoadFailed(wish.message))

            is AdminWish.SelectTab    -> Observable.just(AdminEffect.TabSelected(wish.tab))
            is AdminWish.SearchChanged -> Observable.just(AdminEffect.SearchQueryUpdated(wish.query))

            is AdminWish.ApproveUser  -> Observable.just(
                AdminEffect.UserStatusUpdated(wish.userId, AccountStatus.ACTIVE)
            )
            is AdminWish.SuspendUser  -> Observable.just(
                AdminEffect.UserStatusUpdated(wish.userId, AccountStatus.SUSPENDED)
            )
            is AdminWish.EditUser -> Observable.empty()  // handled via News

            is AdminWish.ResolveAlert -> Observable.just(
                AdminEffect.AlertStatusUpdated(wish.alertId, AlertStatus.RESOLVED)
            )
        }
}

// ── Reducer ────────────────────────────────────────────────────────────────────

private class AdminReducer : Reducer<AdminState, AdminEffect> {
    override fun invoke(state: AdminState, effect: AdminEffect): AdminState = when (effect) {
        AdminEffect.LoadingStarted         -> state.copy(isLoading = true, error = null)
        is AdminEffect.DataLoaded          -> state.copy(
            isLoading = false,
            users = effect.users,
            alerts = effect.alerts,
            pendingApprovalCount = effect.users.count { it.status == AccountStatus.PENDING_APPROVAL },
            activeAlertCount = effect.alerts.count { it.status == AlertStatus.ACTIVE },
        )
        is AdminEffect.LoadFailed          -> state.copy(isLoading = false, error = effect.message)
        is AdminEffect.TabSelected         -> state.copy(tab = effect.tab)
        is AdminEffect.SearchQueryUpdated  -> state.copy(searchQuery = effect.query)
        is AdminEffect.UserStatusUpdated   -> state.copy(
            users = state.users.map {
                if (it.userId == effect.userId) it.copy(status = effect.status) else it
            },
            pendingApprovalCount = state.users.count { u ->
                if (u.userId == effect.userId) effect.status == AccountStatus.PENDING_APPROVAL
                else u.status == AccountStatus.PENDING_APPROVAL
            },
        )
        is AdminEffect.AlertStatusUpdated  -> state.copy(
            alerts = state.alerts.map {
                if (it.alertId == effect.alertId) it.copy(status = effect.status) else it
            },
        )
        is AdminEffect.LiveAlertReceived   -> state.copy(
            alerts = listOf(effect.entry) + state.alerts,
            activeAlertCount = state.activeAlertCount + 1,
        )
    }
}

// ── NewsPublisher ──────────────────────────────────────────────────────────────

private class AdminNewsPublisher :
    NewsPublisher<AdminWish, AdminEffect, AdminState, AdminNews> {
    override fun invoke(wish: AdminWish, effect: AdminEffect, state: AdminState): AdminNews? =
        when {
            wish is AdminWish.EditUser -> AdminNews.NavigateToEditUser(wish.userId)
            effect is AdminEffect.UserStatusUpdated && effect.status == AccountStatus.ACTIVE ->
                AdminNews.ShowToast("User approved successfully.")
            effect is AdminEffect.UserStatusUpdated && effect.status == AccountStatus.SUSPENDED ->
                AdminNews.ShowToast("User suspended.")
            else -> null
        }
}

// ── Feature ────────────────────────────────────────────────────────────────────

class AdminFeature : BaseFeature<AdminWish, AdminWish, AdminEffect, AdminState, AdminNews>(
    initialState  = AdminState(),
    wishToAction  = { it },
    actor         = AdminActor(),
    reducer       = AdminReducer(),
    newsPublisher = AdminNewsPublisher(),
    bootstrapper  = object : Bootstrapper<AdminWish> {
        override fun invoke(): Observable<AdminWish> = Observable.just(AdminWish.LoadAll)
    },
)
