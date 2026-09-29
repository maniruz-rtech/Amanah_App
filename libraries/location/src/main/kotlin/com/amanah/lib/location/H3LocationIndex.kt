package com.amanah.lib.location

import com.uber.h3core.H3Core
import com.uber.h3core.util.LatLng

/**
 * Stateless H3 facade used throughout the Node tree.
 *
 * Thread-safe: [H3Core.newInstance] returns a stateless singleton internally.
 *
 * All heavy calls (gridDisk, etc.) are CPU-bound; callers must dispatch to
 * an ioScheduler or computationScheduler — never call from the main thread.
 */
object H3LocationIndex {

    private val h3: H3Core by lazy { H3Core.newInstance() }

    // ── Encoding ──────────────────────────────────────────────────────────────

    fun encode(lat: Double, lng: Double, resolution: Int = H3Resolution.DISTRICT): String =
        h3.latLngToCellAddress(lat, lng, resolution)

    fun decode(cellAddress: String): LatLng =
        h3.cellToLatLng(cellAddress)

    // ── Proximity ─────────────────────────────────────────────────────────────

    /**
     * Returns all H3 addresses within [kRings] k-rings of the cell that
     * contains [lat]/[lng]. The origin cell is always included (k=0).
     *
     * Used by [ProximityMatcher] to find responders for an emergency alert:
     *   kRings=1 → 7 cells, urban coverage ~5 km
     *   kRings=2 → 19 cells, rural coverage ~10 km
     */
    fun nearbyAddresses(
        lat: Double,
        lng: Double,
        resolution: Int = H3Resolution.DISTRICT,
        kRings: Int = H3Resolution.EMERGENCY_K_RING,
    ): Set<String> {
        val origin = encode(lat, lng, resolution)
        return h3.gridDisk(origin, kRings).toHashSet()
    }

    /**
     * Returns the grid distance (in hops) between two cells at the same
     * resolution. Used as a fast pre-filter before exact Haversine.
     */
    fun gridDistance(addressA: String, addressB: String): Long =
        h3.gridDistance(addressA, addressB)

    /**
     * Returns true if [otherLat]/[otherLng] falls within [kRings] k-rings of
     * the cell containing [originLat]/[originLng] at [resolution].
     *
     * Allocation-free version: avoids building the full ring set if possible.
     */
    fun isWithinKRings(
        originLat: Double, originLng: Double,
        otherLat: Double, otherLng: Double,
        resolution: Int = H3Resolution.DISTRICT,
        kRings: Int = H3Resolution.EMERGENCY_K_RING,
    ): Boolean {
        val origin = encode(originLat, originLng, resolution)
        val other  = encode(otherLat, otherLng, resolution)
        if (origin == other) return true
        return try {
            gridDistance(origin, other) <= kRings
        } catch (_: Exception) {
            false // Pentagon edge case — treat as out of range
        }
    }

    /** Returns the compact list of child cells at [childResolution] for a parent cell. */
    fun childCells(parentAddress: String, childResolution: Int): List<String> =
        h3.cellToChildren(parentAddress, childResolution)

    /**
     * Returns the boundary vertices of [cellAddress] as a list of [LatLng] pairs,
     * in order suitable for drawing a polygon overlay.
     *
     * Used by [AmanahDebugDrawer] to render geoshard boundaries on the debug map
     * overlay so engineers can visually verify k-ring coverage during QA.
     *
     * CPU-bound — call from ioScheduler / computationScheduler.
     */
    fun cellBoundary(cellAddress: String): List<LatLng> =
        h3.cellToBoundary(cellAddress)

    /**
     * Returns boundary vertices for every cell in [cellAddresses]. Convenience
     * wrapper used by the debug drawer to draw all searched shard boundaries.
     */
    fun cellBoundaries(cellAddresses: Set<String>): Map<String, List<LatLng>> =
        cellAddresses.associateWith { cellBoundary(it) }
}
