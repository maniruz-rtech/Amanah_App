package com.amanah.feature.admin.node.userdetail

import com.amanah.feature.admin.repository.AdminRepository
import com.amanah.feature.auth.model.AccountStatus
import com.amanah.feature.auth.model.UserRole
import com.amanah.feature.core.network.UserProfileDto
import com.amanah.feature.core.repository.Outcome
import com.amanah.lib.nodes.Interactor
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class AdminUserDetailInteractor(
    private val userId: String,
    private val repository: AdminRepository? = null,
) : Interactor<AdminUserDetailView, AdminUserDetailRouter>() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var current = AdminUserDetailState(userId = userId, isLoading = true)

    override fun onAttach() {
        view?.render(current)
        repository?.let { reload(it) }

        view?.events = { event ->
            when (event) {
                AdminUserDetailEvent.Back ->
                    router?.onBack()

                AdminUserDetailEvent.Approve ->
                    mutateStatus(AccountStatus.ACTIVE)

                AdminUserDetailEvent.Suspend ->
                    mutateStatus(AccountStatus.SUSPENDED)

                is AdminUserDetailEvent.RevokeDevice -> {
                    current = current.copy(
                        devices = current.devices.filterNot { it.deviceId == event.deviceId },
                    )
                    view?.render(current)
                    router?.onUserUpdated(userId)
                }

                AdminUserDetailEvent.ResetPassword -> {
                    // No direct backend endpoint yet — surface via news / snackbar
                    router?.onUserUpdated(userId)
                }
            }
        }
    }

    override fun onDetach() {
        view?.events = null
        scope.cancel()
    }

    private fun mutateStatus(newStatus: AccountStatus) {
        val repo = repository ?: return
        current = current.copy(isMutating = true)
        view?.render(current)
        scope.launch {
            val outcome = when (newStatus) {
                AccountStatus.ACTIVE     -> repo.approveUser(userId)
                AccountStatus.SUSPENDED  -> repo.suspendUser(userId, reason = "admin_action")
                AccountStatus.PENDING_APPROVAL -> Outcome.Success(Unit)  // no path
            }
            if (outcome is Outcome.Success) {
                reload(repo)
                router?.onUserUpdated(userId)
            } else {
                current = current.copy(isMutating = false)
                view?.render(current)
            }
        }
    }

    private fun reload(repo: AdminRepository) {
        scope.launch {
            when (val outcome = repo.getUser(userId)) {
                is Outcome.Success -> {
                    current = outcome.value.toState()
                    view?.render(current)
                }
                else -> {
                    current = current.copy(isLoading = false, isMutating = false)
                    view?.render(current)
                }
            }
        }
    }

    private fun UserProfileDto.toState(): AdminUserDetailState =
        AdminUserDetailState(
            userId         = id,
            isLoading      = false,
            isMutating     = false,
            displayName    = displayName ?: username,
            email          = email,
            phone          = phone,
            role           = if (roles.any { it in ADMIN_ROLE_NAMES }) UserRole.ADMIN else UserRole.USER,
            status         = when {
                isSuspended  -> AccountStatus.SUSPENDED
                !isVerified  -> AccountStatus.PENDING_APPROVAL
                else         -> AccountStatus.ACTIVE
            },
            createdAt      = System.currentTimeMillis(),  // ISO parse in next iteration
            lastLoginAt    = null,
            devices        = emptyList(),
            recentActivity = emptyList(),
        )

    private companion object {
        val ADMIN_ROLE_NAMES = setOf("super_admin", "regional_admin", "admin", "ADMIN")
    }
}
