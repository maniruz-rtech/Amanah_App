package com.amanah.feature.core.location

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.os.BatteryManager
import android.util.Log
import androidx.core.content.ContextCompat
import com.amanah.lib.location.H3LocationIndex
import com.amanah.lib.location.H3Resolution
import com.badoo.reaktive.observable.Observable
import com.badoo.reaktive.subject.publish.PublishSubject
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import java.util.concurrent.atomic.AtomicReference

/**
 * Production [LocationProvider] backed by Google Play Services'
 * `FusedLocationProviderClient`.
 *
 * Behaviour:
 *   - Adapts the location-request cadence based on the active
 *     [TrackingProfile] (see [TrackingProfile.intervalMs]).
 *   - Computes both the DISTRICT (res 7) and BLOCK (res 9) H3 cells for
 *     every fix so callers don't repeat the work.
 *   - Best-effort battery-level snapshot per fix via [BatteryManager].
 *   - Permission-aware: [start] is a no-op if neither
 *     `ACCESS_FINE_LOCATION` nor `ACCESS_COARSE_LOCATION` is granted. The
 *     gateway then surfaces a `NoFix` state to the UI so the user is
 *     prompted to grant permission.
 *
 * Thread-safety: all mutations to internal state use volatile fields plus
 * `AtomicReference` for the snapshot. FusedLocationProviderClient runs its
 * callback on the main looper by default; we honour that contract.
 */
class FusedLocationProvider(
    private val appContext: Context,
) : LocationProvider {

    private val client: FusedLocationProviderClient =
        LocationServices.getFusedLocationProviderClient(appContext)

    private val subject = PublishSubject<LocationFix>()
    override val stream: Observable<LocationFix> = subject

    private val lastFix = AtomicReference<LocationFix?>(null)

    @Volatile private var activeProfile: TrackingProfile? = null
    @Volatile private var activeCallback: LocationCallback? = null

    override fun snapshot(): LocationFix? = lastFix.get()

    override fun currentH3Cell(resolution: Int): String? {
        val fix = lastFix.get() ?: return null
        return when (resolution) {
            H3Resolution.DISTRICT -> fix.h3
            H3Resolution.BLOCK    -> fix.h3Block
            else -> H3LocationIndex.encode(fix.lat, fix.lng, resolution)
        }
    }

    @SuppressLint("MissingPermission")
    override fun start(profile: TrackingProfile) {
        if (!hasLocationPermission()) {
            Log.w(TAG, "start($profile) skipped — no location permission")
            return
        }

        // Idempotent: same profile + active callback ⇒ no-op.
        if (activeProfile == profile && activeCallback != null) return

        // Switch profile cleanly.
        stop()

        val request = LocationRequest.Builder(profile.intervalMs)
            .setMinUpdateIntervalMillis(profile.fastestIntervalMs)
            .setMinUpdateDistanceMeters(profile.minDisplacementM)
            .setPriority(profile.toGmsPriority())
            .build()

        val callback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                val last = result.lastLocation ?: return
                val battery = readBatteryLevel()
                val h3District = runCatching {
                    H3LocationIndex.encode(last.latitude, last.longitude, H3Resolution.DISTRICT)
                }.getOrDefault("")
                val h3Block = runCatching {
                    H3LocationIndex.encode(last.latitude, last.longitude, H3Resolution.BLOCK)
                }.getOrDefault("")

                val fix = LocationFix(
                    lat          = last.latitude,
                    lng          = last.longitude,
                    accuracyM    = if (last.hasAccuracy()) last.accuracy else Float.NaN,
                    fixedAtMs    = System.currentTimeMillis(),
                    h3           = h3District,
                    h3Block      = h3Block,
                    batteryLevel = battery,
                )
                lastFix.set(fix)
                subject.onNext(fix)
            }
        }

        client.requestLocationUpdates(request, callback, appContext.mainLooper)
        activeCallback = callback
        activeProfile = profile
    }

    override fun stop() {
        activeCallback?.let { client.removeLocationUpdates(it) }
        activeCallback = null
        activeProfile = null
    }

    // ── helpers ────────────────────────────────────────────────────────────────

    private fun hasLocationPermission(): Boolean {
        val fine = ContextCompat.checkSelfPermission(
            appContext, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(
            appContext, Manifest.permission.ACCESS_COARSE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        return fine || coarse
    }

    private fun readBatteryLevel(): Int? = runCatching {
        val bm = appContext.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager
        bm?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)?.takeIf { it in 0..100 }
    }.getOrNull()

    private fun TrackingProfile.toGmsPriority(): Int = when (this) {
        TrackingProfile.IDLE      -> Priority.PRIORITY_BALANCED_POWER_ACCURACY
        TrackingProfile.ACTIVE    -> Priority.PRIORITY_HIGH_ACCURACY
        TrackingProfile.EMERGENCY -> Priority.PRIORITY_HIGH_ACCURACY
    }

    private companion object {
        const val TAG = "FusedLocationProvider"
    }
}
