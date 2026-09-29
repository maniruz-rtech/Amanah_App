package com.amanah.feature.core.realtime

import android.content.Context
import android.util.Log
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import java.util.concurrent.ConcurrentLinkedDeque

/**
 * Process-death-resilient outbound queue.
 *
 * Backs the in-memory FIFO with a Jetpack DataStore Preferences file. Every
 * mutation snapshots the queue to disk; on process start the queue is
 * restored. Crucially, this means an SOS triggered in airplane mode that
 * outlives the app process still flushes once connectivity returns.
 *
 * Storage format: a single JSON-encoded list of [PersistedEntry] under the
 * key `outbound_queue`. Acceptable because:
 *   - Queue size is bounded by gateway flush cadence (rarely > a few items).
 *   - We need atomic snapshot semantics — DataStore Preferences guarantees
 *     atomic writes; protobuf-backed datastore would also work but adds a
 *     codegen step.
 *
 * Threading: writes happen on [Dispatchers.IO] via a SupervisorJob scope.
 * Reads from [drainEligible] are synchronous via an in-memory mirror; the
 * mirror is hydrated lazily and synchronously on first access (boot-only
 * cost ≈ a few ms on Pixel 7).
 *
 * Drop-in compatible with the in-memory [OutboundQueue] — same public
 * surface so callers don't change. Constructor takes a [Context] so the
 * caller can decide where to instantiate it.
 */
class DurableOutboundQueue(
    appContext: Context,
    private val gson: Gson = Gson(),
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO),
) : OutboundQueue {

    private data class PersistedEntry(
        val envelope: RealtimeEnvelope,
        val enqueuedAtMs: Long,
    )

    private val dataStore: DataStore<Preferences> = appContext.outboundQueueDataStore
    private val mirror = ConcurrentLinkedDeque<PersistedEntry>()
    @Volatile private var initialised = false

    init {
        // Eagerly hydrate from disk on first construction. Blocking — but
        // happens once per process lifetime (≤ 5 ms on a Pixel 7).
        runCatching {
            runBlocking { hydrate() }
            initialised = true
        }.onFailure {
            Log.w(TAG, "hydrate failed; starting empty ($it)")
            initialised = true
        }
    }

    override fun enqueue(envelope: RealtimeEnvelope) {
        val entry = PersistedEntry(envelope, System.currentTimeMillis())
        mirror.addLast(entry)
        scheduleSnapshot()
    }

    /**
     * Drain entries whose TTL has not yet expired. Expired entries are
     * dropped and their `eventId`s are returned in [OutboundQueue.Drain.expired].
     */
    override fun drainEligible(nowMs: Long): OutboundQueue.Drain {
        val live    = mutableListOf<RealtimeEnvelope>()
        val expired = mutableListOf<String>()
        while (true) {
            val entry = mirror.pollFirst() ?: break
            val ttl   = entry.envelope.ttlMs
            val expiresAt = if (ttl == null) Long.MAX_VALUE else entry.enqueuedAtMs + ttl
            if (nowMs >= expiresAt) expired += entry.envelope.eventId
            else                    live    += entry.envelope
        }
        scheduleSnapshot()
        return OutboundQueue.Drain(live, expired)
    }

    override fun isEmpty(): Boolean = mirror.isEmpty()
    override fun size():    Int      = mirror.size

    override fun clear() {
        mirror.clear()
        scheduleSnapshot()
    }

    // ── Persistence ────────────────────────────────────────────────────────────

    private suspend fun hydrate() {
        val prefs = dataStore.data.first()
        val raw   = prefs[KEY_QUEUE] ?: return
        val type  = object : TypeToken<List<PersistedEntry>>() {}.type
        val list  = runCatching { gson.fromJson<List<PersistedEntry>>(raw, type) }
            .getOrNull()
            .orEmpty()
        list.forEach { mirror.addLast(it) }
    }

    private fun scheduleSnapshot() {
        if (!initialised) return
        val current = mirror.toList()
        val json    = gson.toJson(current)
        scope.launch {
            dataStore.edit { prefs -> prefs[KEY_QUEUE] = json }
        }
    }

    private companion object {
        const val TAG = "DurableOutboundQueue"
        val KEY_QUEUE = stringPreferencesKey("outbound_queue")
    }
}

private val Context.outboundQueueDataStore by preferencesDataStore(name = "amanah_outbound_queue")
