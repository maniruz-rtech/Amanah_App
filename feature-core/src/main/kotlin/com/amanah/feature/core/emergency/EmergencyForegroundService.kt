package com.amanah.feature.core.emergency

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat

/**
 * Foreground service that keeps the app process alive while an emergency
 * is active.
 *
 * Why this exists:
 *   - Without a foreground service the Android system can kill the app's
 *     process under memory pressure, severing the realtime WebSocket and
 *     stopping the location updates that feed responders.
 *   - During an active emergency we need the process to remain reliable
 *     **at the cost of a persistent notification** — which is the contract
 *     Android offers in exchange for these guarantees.
 *
 * Lifecycle:
 *   - [start] is called from `EmergencyAlertEngine` when the FSM enters
 *     any active phase. Subsequent calls are coalesced into one running
 *     service.
 *   - [stop] is called when the FSM transitions back to IDLE (resolved,
 *     cancelled, error). The service tears down the notification.
 *
 * Implementation notes:
 *   - `foregroundServiceType="location|specialUse"` is declared in the
 *     manifest. The location flag tells Android we'll keep collecting
 *     locations (real); specialUse is the Android-14 catch-all required
 *     for app-defined long-running uses.
 *   - The service itself doesn't talk to the realtime gateway — it just
 *     anchors the process. The gateway runs in its own executor and
 *     resumes naturally because the process stays alive.
 */
class EmergencyForegroundService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null   // started service, not bound

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val alertId = intent?.getStringExtra(EXTRA_ALERT_ID) ?: "unknown"
        Log.i(TAG, "onStartCommand alertId=$alertId")
        startForeground(NOTIFICATION_ID, buildNotification(alertId))
        return START_STICKY
    }

    override fun onDestroy() {
        Log.i(TAG, "onDestroy")
        super.onDestroy()
    }

    // ── Notification ───────────────────────────────────────────────────────────

    private fun buildNotification(alertId: String): Notification {
        ensureChannel()

        val launch = packageManager.getLaunchIntentForPackage(packageName)
            ?.apply { flags = Intent.FLAG_ACTIVITY_NEW_TASK }
        val pi = launch?.let {
            PendingIntent.getActivity(
                this, 0, it,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        }

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("Emergency in progress")
            .setContentText("Amanah is tracking the incident in the background")
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .apply { if (pi != null) setContentIntent(pi) }
            .build()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (mgr.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Active emergency",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "Shown while you have an active emergency. Cannot be dismissed."
            setSound(null, null)
            enableVibration(false)
        }
        mgr.createNotificationChannel(channel)
    }

    companion object {
        private const val TAG             = "EmergencyFgService"
        private const val NOTIFICATION_ID = 0xA1A1
        private const val CHANNEL_ID      = "amanah_emergency_fg"
        const val EXTRA_ALERT_ID          = "alert_id"

        /** Starts the service. Idempotent — re-start with a new alertId updates the notification. */
        fun start(ctx: Context, alertId: String) {
            val intent = Intent(ctx, EmergencyForegroundService::class.java)
                .putExtra(EXTRA_ALERT_ID, alertId)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ctx.startForegroundService(intent)
            } else {
                ctx.startService(intent)
            }
        }

        /** Tears down the service. Idempotent. */
        fun stop(ctx: Context) {
            val intent = Intent(ctx, EmergencyForegroundService::class.java)
            ctx.stopService(intent)
        }
    }
}
