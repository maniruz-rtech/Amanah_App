package com.amanah.feature.user.node.dashboard

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.key
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.amanah.feature.user.mvi.ResponderInfo
import com.badoo.mobile.util.WeakHandler
import com.google.android.gms.maps.CameraUpdateFactory
import com.google.android.gms.maps.model.BitmapDescriptorFactory
import com.google.android.gms.maps.model.LatLng
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.MapProperties
import com.google.maps.android.compose.MapType
import com.google.maps.android.compose.MapUiSettings
import com.google.maps.android.compose.Marker
import com.google.maps.android.compose.MarkerState
import com.google.maps.android.compose.rememberCameraPositionState
import kotlinx.coroutines.launch

// ── Camera animation constants ─────────────────────────────────────────────────

private const val MAP_ZOOM_EMERGENCY = 15f
private const val CAMERA_ANIMATE_MS  = 1_200
private const val CAMERA_DELAY_MS    = 300L

// ── ETA thresholds for marker colour ──────────────────────────────────────────

private const val ETA_FAST_SECONDS   = 5 * 60   // < 5 min → green
private const val ETA_MEDIUM_SECONDS = 10 * 60  // < 10 min → yellow

/**
 * Full-screen emergency map composable.
 *
 * Displays:
 *   • A red victim anchor marker at [victimLat]/[victimLng].
 *   • One marker per [responders] entry, colour-coded by ETA:
 *       – Green  : ETA < 5 min (or null — unknown, default hopeful colour)
 *       – Yellow : ETA 5–10 min
 *       – Orange : ETA > 10 min
 *
 * Camera animation:
 *   The initial fly-to uses [WeakHandler.postDelayed] with a 300 ms delay to give
 *   the tile layer time to load before animating. The handler holds a weak reference
 *   to the caller (via the Badoo WeakHandler contract), so MainActivity can be GC'd
 *   if the user background-kills the app before the delay fires.
 *   [DisposableEffect] cancels the pending runnable if this composable leaves the
 *   composition early — preventing a camera animate on a recycled map.
 *
 * 60 fps strategy:
 *   • Each [Marker] is keyed by [ResponderInfo.responderId]; only the changed marker
 *     is recomposed on position update, not the entire map content.
 *   • [rememberUpdatedState] captures the responder list so lambdas inside markers
 *     always see fresh state without triggering a full GoogleMap recomposition.
 *   • [MapUiSettings] disables the map toolbar (which would spawn a Google Maps
 *     intent) and keeps zoom controls reachable for responders on-foot.
 *
 * Privacy note: [victimLat]/[victimLng] must only be supplied when
 * [EmergencyState.isActiveEmergency] is true — the caller ([UserDashboardView]) is
 * responsible for this gate.
 */
@Composable
fun ResponderMapView(
    victimLat: Double,
    victimLng: Double,
    responders: List<ResponderInfo>,
    weakHandler: WeakHandler,
    modifier: Modifier = Modifier,
) {
    val cameraPositionState = rememberCameraPositionState()
    val scope               = rememberCoroutineScope()
    val victimLatLng        = remember(victimLat, victimLng) { LatLng(victimLat, victimLng) }

    // Capture the latest responder list without causing a GoogleMap recomposition.
    val currentResponders = rememberUpdatedState(responders)

    // ── Delayed WeakHandler camera fly-to ─────────────────────────────────────
    // Re-fires whenever the victim position changes (e.g., server corrects GPS).
    DisposableEffect(victimLat, victimLng) {
        val runnable = Runnable {
            scope.launch {
                cameraPositionState.animate(
                    update      = CameraUpdateFactory.newLatLngZoom(victimLatLng, MAP_ZOOM_EMERGENCY),
                    durationMs  = CAMERA_ANIMATE_MS,
                )
            }
        }
        weakHandler.postDelayed(runnable, CAMERA_DELAY_MS)
        onDispose { weakHandler.removeCallbacks(runnable) }
    }

    GoogleMap(
        modifier             = modifier,
        cameraPositionState  = cameraPositionState,
        properties           = MapProperties(mapType = MapType.NORMAL),
        uiSettings           = MapUiSettings(
            mapToolbarEnabled     = false,  // prevents accidental Google Maps launch
            zoomControlsEnabled   = true,
            myLocationButtonEnabled = false,
        ),
    ) {
        // ── Victim anchor marker ───────────────────────────────────────────────
        Marker(
            state   = MarkerState(position = victimLatLng),
            title   = "Emergency Location",
            snippet = "Victim needs assistance",
            icon    = BitmapDescriptorFactory.defaultMarker(BitmapDescriptorFactory.HUE_RED),
        )

        // ── Responder markers (keyed for minimal recomposition) ───────────────
        currentResponders.value.forEach { responder ->
            key(responder.responderId) {
                val position = LatLng(responder.lat, responder.lng)
                val hue      = responderMarkerHue(responder.etaSeconds)
                val snippet  = buildResponderSnippet(responder)

                Marker(
                    state   = MarkerState(position = position),
                    title   = "Responder",
                    snippet = snippet,
                    icon    = BitmapDescriptorFactory.defaultMarker(hue),
                )
            }
        }
    }
}

// ── ETA marker colour mapping ──────────────────────────────────────────────────

private fun responderMarkerHue(etaSeconds: Int?): Float = when {
    etaSeconds == null                -> BitmapDescriptorFactory.HUE_AZURE   // calculating
    etaSeconds < ETA_FAST_SECONDS     -> BitmapDescriptorFactory.HUE_GREEN
    etaSeconds < ETA_MEDIUM_SECONDS   -> BitmapDescriptorFactory.HUE_YELLOW
    else                              -> BitmapDescriptorFactory.HUE_ORANGE
}

private fun buildResponderSnippet(responder: ResponderInfo): String {
    val etaPart  = responder.etaSeconds?.let { "ETA: ${formatEta(it)}" } ?: "Calculating ETA…"
    val distPart = responder.distanceMeters?.let { "${formatDistance(it)} away" } ?: ""
    return listOf(etaPart, distPart).filter { it.isNotEmpty() }.joinToString(" · ")
}

// ── ETA card ───────────────────────────────────────────────────────────────────

/**
 * Declarative card showing the nearest responder's distance and ETA.
 * Distances are already rounded to the nearest 100 m by the engine before
 * arriving here — no additional rounding is applied.
 *
 * Shows a [CircularProgressIndicator] while ETA is still being calculated.
 */
@Composable
fun EtaCard(
    etaSeconds: Int?,
    distanceMeters: Int?,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier,
        colors   = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.secondaryContainer,
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
    ) {
        Row(
            modifier              = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp, vertical = 14.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment     = Alignment.CenterVertically,
        ) {
            // ── Distance cell ──────────────────────────────────────────────────
            EtaCell(
                icon  = Icons.Default.Place,
                label = "Distance",
                value = distanceMeters?.let { formatDistance(it) } ?: "—",
                tint  = MaterialTheme.colorScheme.error,
            )

            // ── Divider ────────────────────────────────────────────────────────
            Spacer(Modifier.width(1.dp))

            // ── ETA cell ───────────────────────────────────────────────────────
            if (etaSeconds != null) {
                EtaCell(
                    icon  = Icons.Default.Schedule,
                    label = "ETA",
                    value = formatEta(etaSeconds),
                    tint  = etaColour(etaSeconds),
                )
            } else {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(
                        modifier  = Modifier.size(20.dp),
                        strokeWidth = 2.dp,
                        color     = MaterialTheme.colorScheme.onSecondaryContainer,
                    )
                    Text(
                        text  = "Calculating ETA",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSecondaryContainer,
                    )
                }
            }

            // ── Responder en-route indicator ───────────────────────────────────
            if (etaSeconds != null) {
                EtaCell(
                    icon  = Icons.Default.DirectionsCar,
                    label = "Responder",
                    value = "En route",
                    tint  = Color(0xFF4CAF50),
                )
            }
        }
    }
}

@Composable
private fun EtaCell(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    value: String,
    tint: Color,
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(
            imageVector  = icon,
            contentDescription = label,
            tint         = tint,
            modifier     = Modifier.size(22.dp),
        )
        Text(
            text  = value,
            style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
            color = MaterialTheme.colorScheme.onSecondaryContainer,
        )
        Text(
            text  = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = 0.7f),
        )
    }
}

// ── Formatting helpers ─────────────────────────────────────────────────────────

internal fun formatEta(seconds: Int): String {
    val mins = seconds / 60
    return when {
        mins < 1  -> "<1 min"
        mins == 1 -> "1 min"
        else      -> "$mins min"
    }
}

internal fun formatDistance(meters: Int): String =
    if (meters >= 1_000) "${"%.1f".format(meters / 1_000.0)} km"
    else "$meters m"

@Composable
private fun etaColour(etaSeconds: Int): Color = when {
    etaSeconds < ETA_FAST_SECONDS   -> Color(0xFF4CAF50)  // green
    etaSeconds < ETA_MEDIUM_SECONDS -> Color(0xFFFFC107)  // amber
    else                            -> Color(0xFFFF5722)  // deep-orange
}
