package com.amanah.lib.location

/**
 * Immutable snapshot of a device location.
 *
 * [isExact] controls the privacy contract:
 *   false → coordinates have been run through [LocationPrivacyFilter.obfuscate]; safe to broadcast
 *   true  → raw GPS; only transmitted during an active emergency
 */
data class LocationUpdate(
    val lat: Double,
    val lng: Double,
    val accuracyMeters: Float = 0f,
    val timestampMs: Long = System.currentTimeMillis(),
    val isExact: Boolean = false,
) {
    /** H3-encoded cell address at the given resolution; computed lazily. */
    fun h3Cell(resolution: Int = H3Resolution.DISTRICT): String =
        H3LocationIndex.encode(lat, lng, resolution)
}
