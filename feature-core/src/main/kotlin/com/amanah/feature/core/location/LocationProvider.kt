package com.amanah.feature.core.location

import com.amanah.lib.location.H3Resolution
import com.badoo.reaktive.observable.Observable

/**
 * Process-wide source of the user's current location.
 *
 * Two observation modes:
 *  - [snapshot]: get the last-known location synchronously (best-effort).
 *    Used when the user triggers SOS — we cannot wait for a fresh fix.
 *  - [stream]:   subscribe to a hot stream of [LocationFix]es. The provider
 *    chooses the cadence based on [TrackingProfile] supplied to [start].
 *
 * Lifecycle:
 *  - [start] kicks the provider into the requested profile. Idempotent.
 *  - [stop] releases all subscriptions and stops collecting locations.
 *  - During an active emergency the caller asks for [TrackingProfile.EMERGENCY]
 *    (sub-second cadence, high accuracy). Otherwise [TrackingProfile.IDLE]
 *    (60s cadence, balanced accuracy) preserves battery.
 *
 * Privacy:
 *  - [LocationFix.h3] is computed from the raw coordinates at the requested
 *    resolution. Callers that only need the H3 cell should read it directly
 *    rather than re-deriving from lat/lng.
 *  - Raw GPS is only surfaced to consumers that explicitly need it
 *    (EmergencyAlertEngine). The presence-ping path uses [LocationFix.h3]
 *    alone.
 */
interface LocationProvider {

    val stream: Observable<LocationFix>

    /** Last-known fix or null if none yet. Hot path; non-blocking. */
    fun snapshot(): LocationFix?

    /** Switch to a new tracking profile. Safe to call repeatedly. */
    fun start(profile: TrackingProfile)

    /** Stop all collection; clears the in-memory snapshot. */
    fun stop()

    /**
     * Compute the H3 cell for the current snapshot at the requested
     * resolution, or null if no snapshot exists yet.
     */
    fun currentH3Cell(resolution: Int = H3Resolution.DISTRICT): String?
}

/**
 * A timestamped location fix.
 *
 * @param lat       raw WGS84 latitude
 * @param lng       raw WGS84 longitude
 * @param accuracyM accuracy radius in metres (provider-supplied)
 * @param fixedAtMs wall-clock epoch when the fix was captured
 * @param h3        H3 cell at [H3Resolution.DISTRICT] (resolution 7)
 * @param h3Block   H3 cell at [H3Resolution.BLOCK] (resolution 9)
 * @param batteryLevel device battery 0..100, or null if unknown
 */
data class LocationFix(
    val lat: Double,
    val lng: Double,
    val accuracyM: Float,
    val fixedAtMs: Long,
    val h3: String,
    val h3Block: String,
    val batteryLevel: Int? = null,
)

/**
 * Battery-aware tracking strategies.
 *
 *   IDLE       — passive; 60s cadence, balanced accuracy. The default.
 *   ACTIVE     — user opened the app foreground; 10s cadence, high accuracy.
 *   EMERGENCY  — active alert in progress; 1s cadence, finest accuracy
 *                Google Play Services will give us.
 */
enum class TrackingProfile {
    IDLE,
    ACTIVE,
    EMERGENCY,
    ;

    val intervalMs: Long
        get() = when (this) {
            IDLE       -> 60_000L
            ACTIVE     -> 10_000L
            EMERGENCY  -> 1_000L
        }

    val fastestIntervalMs: Long
        get() = when (this) {
            IDLE       -> 30_000L
            ACTIVE     -> 5_000L
            EMERGENCY  -> 500L
        }

    /** Min displacement before another fix is delivered. 0 = always. */
    val minDisplacementM: Float
        get() = when (this) {
            IDLE       -> 50f
            ACTIVE     -> 10f
            EMERGENCY  -> 0f
        }

    val priority: Int
        get() = when (this) {
            IDLE       -> PRIORITY_BALANCED
            ACTIVE     -> PRIORITY_HIGH
            EMERGENCY  -> PRIORITY_HIGH
        }

    private companion object {
        // From com.google.android.gms.location.Priority — mirrored to avoid
        // a hard import in the interface module.
        const val PRIORITY_HIGH     = 100
        const val PRIORITY_BALANCED = 102
    }
}
