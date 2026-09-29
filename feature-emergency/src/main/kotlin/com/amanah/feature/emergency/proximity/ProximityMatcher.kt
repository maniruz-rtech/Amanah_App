package com.amanah.feature.emergency.proximity

import com.amanah.lib.location.H3LocationIndex
import com.amanah.lib.location.H3Resolution
import com.amanah.lib.location.LocationPrivacyFilter

/**
 * Determines which active users should be notified for a given emergency.
 *
 * Algorithm:
 *   1. Encode the victim's coordinates into an H3 cell at [RESOLUTION].
 *   2. Expand a k-ring of [kRings] around that cell to get all candidate cells.
 *   3. Return any [ActiveUser] whose last-known H3 cell is in that set.
 *
 * Privacy: [ActiveUser.h3Cell] is always at resolution 7 (not exact GPS),
 * so this matcher never processes raw coordinates of responders.
 *
 * This class is intentionally stateless — it takes current user snapshots
 * from the caller, which is responsible for caching and refreshing.
 */
object ProximityMatcher {

    const val RESOLUTION = H3Resolution.DISTRICT  // resolution 7, ~5 km²

    data class ActiveUser(
        val userId: String,
        val displayName: String,
        val h3Cell: String,           // at RESOLUTION; never exact GPS
        val fcmToken: String? = null, // for push notification routing
    )

    data class ProximityResult(
        val nearbyUsers: List<ActiveUser>,
        val victimH3Cell: String,
        val searchedCells: Set<String>,
        val kRings: Int,
    )

    /**
     * Returns all [activeUsers] within [kRings] k-rings of the victim's location.
     *
     * CPU-bound: must be called from ioScheduler / computationScheduler.
     *
     * @param victimLat  exact latitude of the victim (from their emergency trigger)
     * @param victimLng  exact longitude of the victim
     * @param activeUsers current snapshot of online users with their H3 cells
     * @param kRings      k-ring expansion (default: 1 for urban, 2 for rural)
     */
    fun findResponders(
        victimLat: Double,
        victimLng: Double,
        activeUsers: List<ActiveUser>,
        kRings: Int = H3Resolution.EMERGENCY_K_RING,
    ): ProximityResult {
        val victimCell = H3LocationIndex.encode(victimLat, victimLng, RESOLUTION)
        val searchCells = H3LocationIndex.nearbyAddresses(victimLat, victimLng, RESOLUTION, kRings)

        val nearby = activeUsers.filter { user ->
            searchCells.contains(user.h3Cell)
        }

        return ProximityResult(
            nearbyUsers   = nearby,
            victimH3Cell  = victimCell,
            searchedCells = searchCells,
            kRings        = kRings,
        )
    }

    /**
     * Checks if a single responder is within range of an alert. Used for
     * incoming alert gating on the client side.
     */
    fun isResponderInRange(
        victimH3Cell: String,
        responderH3Cell: String,
        kRings: Int = H3Resolution.EMERGENCY_K_RING,
    ): Boolean = try {
        H3LocationIndex.gridDistance(victimH3Cell, responderH3Cell) <= kRings
    } catch (_: Exception) {
        false
    }

    // ── Block-level (Resolution 9) precise dispatch ───────────────────────────

    /**
     * Fine-grained responder matching using H3 Resolution 9 (~0.1 km² cells).
     *
     * Hierarchical sharding strategy:
     *   1. District search (res 7, k=1) — broad pass, notifies all candidates.
     *   2. Block search (res 9, k=1) — tight pass for precise dispatch priority.
     *
     * Callers should run the district-level [findResponders] first, then call
     * this method to identify the highest-priority (closest) subset.
     *
     * Requires [ActiveUserFine] with both resolution cells pre-computed — the
     * server should provide these when a user registers their presence.
     *
     * CPU-bound: call from ioScheduler / computationScheduler.
     */
    fun findRespondersBlockLevel(
        victimLat: Double,
        victimLng: Double,
        activeUsers: List<ActiveUserFine>,
        kRings: Int = H3Resolution.EMERGENCY_K_RING,
    ): ProximityResult {
        val victimBlock  = H3LocationIndex.encode(victimLat, victimLng, H3Resolution.BLOCK)
        val searchCells  = H3LocationIndex.nearbyAddresses(victimLat, victimLng, H3Resolution.BLOCK, kRings)

        val nearby = activeUsers
            .filter { user -> searchCells.contains(user.h3CellBlock) }
            .map    { user -> ActiveUser(user.userId, user.displayName, user.h3CellBlock, user.fcmToken) }

        return ProximityResult(
            nearbyUsers   = nearby,
            victimH3Cell  = victimBlock,
            searchedCells = searchCells,
            kRings        = kRings,
        )
    }

    /**
     * Active user model that carries both resolution levels, enabling both the
     * broad district-level notification pass and the precise block-level dispatch.
     */
    data class ActiveUserFine(
        val userId: String,
        val displayName: String,
        val h3CellDistrict: String,  // resolution 7 — used by [findResponders]
        val h3CellBlock: String,     // resolution 9 — used by [findRespondersBlockLevel]
        val fcmToken: String? = null,
    )
}
