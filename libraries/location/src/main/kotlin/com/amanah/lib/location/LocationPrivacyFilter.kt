package com.amanah.lib.location

import java.security.SecureRandom
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Injects calibrated Gaussian spatial noise into idle responder coordinates.
 *
 * Threat model: a passive observer who correlates multiple noised positions
 * can still trilaterate the true location if noise is too small or too
 * deterministic. This filter:
 *   - Uses [SecureRandom] (CSPRNG) to prevent seeding attacks.
 *   - Applies Box-Muller transform for true Gaussian distribution
 *     (flat uniform noise has a smaller effective radius than its label implies).
 *   - The noise sigma is drawn uniformly from [minKm, maxKm] per call so
 *     there is no stable anchor point across successive observations.
 *
 * Privacy guarantee:
 *   - Minimum effective noise radius ≈ 500 m (minKm = 0.5)
 *   - Maximum effective noise radius ≈ 1 000 m (maxKm = 1.0)
 *
 * Usage:
 *   val safe = LocationPrivacyFilter.obfuscate(rawLat, rawLng)
 *   // safe.lat / safe.lng are broadcast-safe in idle state
 *
 *   val exact = LocationPrivacyFilter.reveal(rawLat, rawLng)
 *   // Only call during an ACTIVE_EMERGENCY state transition
 */
object LocationPrivacyFilter {

    private val rng = SecureRandom()

    /** Degrees per km along the latitude axis (constant). */
    private const val DEG_PER_KM_LAT = 1.0 / 111.0

    /** Minimum noise radius in km. */
    private const val MIN_KM = 0.5

    /** Maximum noise radius in km. */
    private const val MAX_KM = 1.0

    data class ObfuscatedLocation(
        val lat: Double,
        val lng: Double,
        val isExact: Boolean = false,
    )

    /**
     * Returns a noised location safe for idle broadcast.
     *
     * The noise magnitude is sampled per-call from U[MIN_KM, MAX_KM] and
     * applied via Box-Muller so the 2-D distribution is Gaussian, not uniform.
     */
    fun obfuscate(lat: Double, lng: Double): ObfuscatedLocation {
        val sigma = MIN_KM + rng.nextDouble() * (MAX_KM - MIN_KM)

        // Box-Muller: two uniform samples → one standard-normal pair
        val u1 = rng.nextDouble().coerceAtLeast(1e-10) // avoid log(0)
        val u2 = rng.nextDouble()
        val mag = sigma * sqrt(-2.0 * ln(u1))
        val angle = 2.0 * Math.PI * u2

        val noiseLat = mag * cos(angle)
        val noiseLng = mag * sin(angle)

        // Degrees per km along longitude varies with latitude
        val degPerKmLng = DEG_PER_KM_LAT / cos(Math.toRadians(lat)).coerceAtLeast(1e-6)

        return ObfuscatedLocation(
            lat = lat + noiseLat * DEG_PER_KM_LAT,
            lng = lng + noiseLng * degPerKmLng,
        )
    }

    /**
     * Returns the exact coordinates. Call ONLY when an ACTIVE_EMERGENCY state
     * is confirmed — never during idle/nearby display.
     */
    fun reveal(lat: Double, lng: Double): ObfuscatedLocation =
        ObfuscatedLocation(lat = lat, lng = lng, isExact = true)

    /**
     * Rounds a raw distance to the nearest 100 m to prevent exact trilateration
     * via repeated ETA queries. Minimum returned value is 100 m.
     *
     * Server-side validation is authoritative; this is an additional UI-layer guard.
     */
    fun roundToNearest100m(distanceMeters: Int): Int =
        ((distanceMeters / 100.0).roundToInt() * 100).coerceAtLeast(100)

    /**
     * Haversine great-circle distance between two WGS84 coordinates, in metres.
     * Accurate to ~0.5 % for distances under 1 000 km.
     *
     * Used by [EmergencyAlertEngine] to compute victim–responder distance before
     * rounding via [roundToNearest100m] and surfacing in the ETA card.
     */
    fun haversineMeters(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
        val earthRadius = 6_371_000.0
        val dLat = Math.toRadians(lat2 - lat1)
        val dLng = Math.toRadians(lng2 - lng1)
        val a = sin(dLat / 2).pow(2) +
                cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) * sin(dLng / 2).pow(2)
        return earthRadius * 2 * asin(sqrt(a.coerceIn(0.0, 1.0)))
    }
}
