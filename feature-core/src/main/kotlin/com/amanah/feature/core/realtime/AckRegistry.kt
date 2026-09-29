package com.amanah.feature.core.realtime

import com.badoo.reaktive.observable.Observable
import com.badoo.reaktive.observable.firstOrError
import com.badoo.reaktive.observable.observable
import com.badoo.reaktive.single.subscribe
import com.badoo.reaktive.subject.publish.PublishSubject
import java.util.concurrent.ConcurrentHashMap

/**
 * Tracks outstanding `eventId`s and the [SendOutcome] observable subscribers
 * expect for each.
 *
 * Lifecycle:
 *   1. [register] called when the gateway sends an envelope.
 *   2. [onAck] called when the server emits an `ack` for that eventId — the
 *      outcome subject completes with [SendOutcome.Acknowledged].
 *   3. [onExpired] called by [OutboundQueue] for envelopes that exceeded TTL
 *      without an ACK — the outcome subject completes with [SendOutcome.Failed].
 *
 * Thread-safety: the registry uses ConcurrentHashMap and Reaktive PublishSubject,
 * both of which are safe under concurrent ACK and send paths.
 */
class AckRegistry {

    private val outcomes = ConcurrentHashMap<String, PublishSubject<SendOutcome>>()

    fun register(eventId: String): Observable<SendOutcome> {
        val subject = outcomes.computeIfAbsent(eventId) { PublishSubject() }
        // First-emission-then-complete shape — the caller doesn't need a Single.
        return observable { emitter ->
            val disposable = subject.firstOrError().subscribe(
                onSuccess = {
                    emitter.onNext(it)
                    emitter.onComplete()
                },
                onError = { emitter.onError(it) },
            )
            emitter.setDisposable(disposable)
        }
    }

    fun onAck(eventId: String) {
        val subject = outcomes.remove(eventId) ?: return
        subject.onNext(SendOutcome.Acknowledged(eventId))
        subject.onComplete()
    }

    fun onExpired(eventId: String, reason: String) {
        val subject = outcomes.remove(eventId) ?: return
        subject.onNext(SendOutcome.Failed(eventId, reason))
        subject.onComplete()
    }

    /** Called on disconnect — every pending ACK is failed with reason 'disconnected'. */
    fun failAll(reason: String) {
        outcomes.keys.toList().forEach { onExpired(it, reason) }
    }

    fun pendingCount(): Int = outcomes.size
}
