package com.amanah.feature.core.debug

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BugReport
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Divider
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * MVICore Time-Travel Debug Drawer.
 *
 * Wraps any Composable with a slide-in debug panel (right edge) that shows:
 *   • Registered MVI Feature names
 *   • Live state-change log (timestamp + feature name + state snapshot)
 *   • H3 geoshard context — current cell ID, resolution, and searched shard set
 *
 * The FAB trigger (bug icon) is shown only when [isEnabled] == true.
 * In release builds, set [isEnabled] = false and the entire overlay and its
 * registrations are stripped by the dead-code elimination pass — zero overhead.
 *
 * Usage (in debug MainActivity.setContent):
 * ```kotlin
 * AmanahDebugDrawer.isEnabled = BuildConfig.DEBUG
 * setContent {
 *     AmanahDebugDrawer.DrawerOverlay {
 *         rootNode.Content()
 *     }
 * }
 * ```
 */
object AmanahDebugDrawer {

    var isEnabled: Boolean = false

    // ── State log ─────────────────────────────────────────────────────────────

    data class StateLogEntry(
        val featureName: String,
        val stateSnapshot: String,
        val timestampMs: Long = System.currentTimeMillis(),
    ) {
        val label: String
            get() = "[${formatTime(timestampMs)}] $featureName"

        private fun formatTime(ms: Long): String {
            val s = (ms / 1000) % 60
            val m = (ms / 60_000) % 60
            val h = (ms / 3_600_000) % 24
            return "%02d:%02d:%02d".format(h, m, s)
        }
    }

    /**
     * Current H3 geoshard context. Updated by [updateH3Context] whenever the
     * active emergency or user presence cell changes.
     *
     * [searchedCells] is the full k-ring set queried for responder matching —
     * engineers can cross-reference it against the responder log to verify that
     * the proximity filter is returning the correct neighbours.
     */
    data class H3DebugContext(
        val cellId: String,
        val resolution: Int,
        val searchedCells: Set<String> = emptySet(),
    )

    private val _log = mutableStateListOf<StateLogEntry>()
    private val _registeredFeatures = mutableListOf<String>()
    private var _h3Context by mutableStateOf<H3DebugContext?>(null)

    // ── Public API ─────────────────────────────────────────────────────────────

    fun registerFeature(featureName: String) {
        if (isEnabled) _registeredFeatures.add(featureName)
    }

    fun unregisterFeature(featureName: String) {
        _registeredFeatures.remove(featureName)
    }

    /**
     * Call from each Feature's Actor or a surrounding Binder to record
     * state transitions for time-travel replay.
     */
    fun recordStateChange(featureName: String, stateSnapshot: Any) {
        if (!isEnabled) return
        _log.add(StateLogEntry(featureName, stateSnapshot.toString()))
        if (_log.size > 500) _log.removeAt(0) // rolling 500-entry window
    }

    /**
     * Updates the H3 geoshard context shown in the drawer's dedicated panel.
     *
     * Call from [UserDashboardInteractor] whenever [EmergencyFeature.states]
     * emits a non-null [victimH3Cell], passing the searched k-ring cells so
     * engineers can visually audit coverage during QA or field testing.
     *
     * Also useful during idle state to confirm the user's own presence cell
     * is encoded at the correct resolution before it is broadcast.
     *
     * No-op when [isEnabled] is false — zero overhead in release builds.
     */
    fun updateH3Context(
        cellId: String,
        resolution: Int,
        searchedCells: Set<String> = emptySet(),
    ) {
        if (!isEnabled) return
        _h3Context = H3DebugContext(cellId, resolution, searchedCells)
    }

    fun clearLog() {
        _log.clear()
        _h3Context = null
    }

    // ── Compose overlay ────────────────────────────────────────────────────────

    @Composable
    fun DrawerOverlay(content: @Composable () -> Unit) {
        if (!isEnabled) {
            content()
            return
        }

        var drawerOpen by remember { mutableStateOf(false) }

        Box(Modifier.fillMaxSize()) {
            // ── App content ───────────────────────────────────────────────────
            content()

            // ── FAB trigger ───────────────────────────────────────────────────
            FloatingActionButton(
                onClick        = { drawerOpen = !drawerOpen },
                modifier       = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(end = 16.dp, bottom = 80.dp),
                containerColor = Color(0xFF6200EE),
            ) {
                Icon(Icons.Default.BugReport, "Debug drawer", tint = Color.White)
            }

            // ── Debug panel ───────────────────────────────────────────────────
            AnimatedVisibility(
                visible  = drawerOpen,
                enter    = slideInHorizontally(initialOffsetX = { it }),
                exit     = slideOutHorizontally(targetOffsetX = { it }),
                modifier = Modifier.align(Alignment.CenterEnd),
            ) {
                DebugPanel(
                    log       = _log.reversed(),
                    features  = _registeredFeatures.toList(),
                    h3Context = _h3Context,
                    onClose   = { drawerOpen = false },
                    onClear   = { clearLog() },
                )
            }
        }
    }

    // ── Panel UI ───────────────────────────────────────────────────────────────

    @Composable
    private fun DebugPanel(
        log: List<StateLogEntry>,
        features: List<String>,
        h3Context: H3DebugContext?,
        onClose: () -> Unit,
        onClear: () -> Unit,
    ) {
        Surface(
            modifier        = Modifier.fillMaxHeight().width(320.dp),
            color           = Color(0xFF1A1A2E).copy(alpha = 0.97f),
            shadowElevation = 16.dp,
        ) {
            Column(Modifier.padding(16.dp)) {

                // ── Header ────────────────────────────────────────────────────
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.BugReport, null, tint = Color(0xFF6200EE))
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "MVICore Time-Travel",
                        color      = Color.White,
                        fontWeight = FontWeight.Bold,
                        fontSize   = 14.sp,
                        modifier   = Modifier.weight(1f),
                    )
                    IconButton(onClick = onClear) {
                        Text("CLR", color = Color(0xFFFF9800), fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    }
                    IconButton(onClick = onClose) {
                        Icon(Icons.Default.Close, "Close", tint = Color.White)
                    }
                }

                Divider(color = Color.White.copy(alpha = 0.15f))
                Spacer(Modifier.height(8.dp))

                // ── Registered features ───────────────────────────────────────
                Text(
                    "Registered Features (${features.size})",
                    color = Color(0xFF76FF03), fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
                )
                features.forEach { name ->
                    Text(
                        "  • $name",
                        color      = Color.White.copy(alpha = 0.7f),
                        fontSize   = 10.sp,
                        fontFamily = FontFamily.Monospace,
                    )
                }

                // ── H3 Geoshard context ───────────────────────────────────────
                if (h3Context != null) {
                    Spacer(Modifier.height(10.dp))
                    Divider(color = Color.White.copy(alpha = 0.10f))
                    Spacer(Modifier.height(6.dp))

                    Text(
                        "H3 Geoshard  (res ${h3Context.resolution})",
                        color      = Color(0xFF00E5FF),
                        fontSize   = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        "  Cell: ${h3Context.cellId}",
                        color      = Color.White.copy(alpha = 0.85f),
                        fontSize   = 10.sp,
                        fontFamily = FontFamily.Monospace,
                    )

                    if (h3Context.searchedCells.isNotEmpty()) {
                        Text(
                            "  Searched: ${h3Context.searchedCells.size} shard(s)",
                            color      = Color.White.copy(alpha = 0.7f),
                            fontSize   = 10.sp,
                            fontFamily = FontFamily.Monospace,
                        )
                        val preview = h3Context.searchedCells.take(4)
                        preview.forEach { cell ->
                            Text(
                                "    ▸ $cell",
                                color      = Color.White.copy(alpha = 0.55f),
                                fontSize   = 9.sp,
                                fontFamily = FontFamily.Monospace,
                            )
                        }
                        val overflow = h3Context.searchedCells.size - preview.size
                        if (overflow > 0) {
                            Text(
                                "    … +$overflow more",
                                color    = Color.White.copy(alpha = 0.4f),
                                fontSize = 9.sp,
                            )
                        }
                    }
                }

                Spacer(Modifier.height(12.dp))
                Divider(color = Color.White.copy(alpha = 0.10f))
                Spacer(Modifier.height(6.dp))

                // ── State log ─────────────────────────────────────────────────
                Text(
                    "State Log (${log.size} entries)",
                    color = Color(0xFF76FF03), fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(4.dp))

                LazyColumn {
                    items(log, key = { it.timestampMs.toString() + it.featureName }) { entry ->
                        StateEntry(entry)
                    }
                }
            }
        }
    }

    @Composable
    private fun StateEntry(entry: StateLogEntry) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 4.dp)
                .background(Color.White.copy(alpha = 0.04f), MaterialTheme.shapes.small)
                .padding(horizontal = 8.dp, vertical = 4.dp),
        ) {
            Text(
                entry.label,
                color      = Color(0xFFFFEB3B),
                fontSize   = 10.sp,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text       = entry.stateSnapshot.take(240) + if (entry.stateSnapshot.length > 240) "…" else "",
                color      = Color.White.copy(alpha = 0.75f),
                fontSize   = 9.sp,
                fontFamily = FontFamily.Monospace,
                lineHeight = 13.sp,
            )
        }
    }
}
