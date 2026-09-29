package com.amanah.feature.core.session

import com.badoo.reaktive.observable.Observable
import com.badoo.reaktive.subject.behavior.BehaviorSubject

/**
 * Minimal session contract.
 *
 * The actual [Session] type is generic on purpose so this module does not
 * depend on `feature-auth` (which would create a cycle). Feature modules
 * supply their own session record via [signIn]; the manager only owns the
 * lifecycle and broadcasts changes.
 *
 * Implemented with a [BehaviorSubject] so any subscriber sees the latest
 * value on subscribe — used by `RootNode` to react to login/logout.
 */
class SessionManager(private val tokenStore: SecureTokenStore) {

    /** Opaque snapshot of the signed-in user (or null if signed out). */
    interface Session {
        val userId: String
        val isAdmin: Boolean
    }

    private val subject = BehaviorSubject<Session?>(null)

    val stream: Observable<Session?> = subject

    val current: Session? get() = subject.value

    val hasSession: Boolean get() = subject.value != null

    fun signIn(session: Session, accessToken: String, refreshToken: String) {
        tokenStore.save(accessToken = accessToken, refreshToken = refreshToken)
        subject.onNext(session)
    }

    fun signOut() {
        tokenStore.clear()
        subject.onNext(null)
    }
}
