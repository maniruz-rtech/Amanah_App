package com.amanah.feature.core.realtime

import java.util.Collections
import java.util.LinkedHashMap

/**
 * Bounded LRU cache of seen inbound `event_id`s.
 *
 * Why this exists: under reconnect, the server may replay events the client
 * already processed (at-least-once delivery semantics). Duplicate handling
 * for the same emergency alert would re-trigger UI state transitions.
 *
 * Size 512 is generous — emergencies are rare; we keep enough memory to
 * survive a multi-minute reconnect storm. Eviction is LRU (oldest dropped
 * when full).
 */
class EventDedup(private val maxEntries: Int = 512) {

    private val seen: MutableMap<String, Boolean> = Collections.synchronizedMap(
        object : LinkedHashMap<String, Boolean>(maxEntries, 0.75f, /* accessOrder = */ true) {
            override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Boolean>?): Boolean =
                size > maxEntries
        }
    )

    /** Returns true if this is the first time we've seen [eventId]; false on duplicate. */
    fun firstSeen(eventId: String): Boolean {
        synchronized(seen) {
            // get() (unlike containsKey) counts as an access in an access-ordered
            // LinkedHashMap, so a replayed id is refreshed to most-recently-used.
            if (seen[eventId] != null) return false
            seen[eventId] = true
            return true
        }
    }

    fun clear() = synchronized(seen) { seen.clear() }

    fun size(): Int = synchronized(seen) { seen.size }
}
