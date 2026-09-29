package com.amanah.feature.core.push

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

/**
 * FCM entry point.
 *
 * Three message classes handled:
 *
 *  - **silent wakeup** (`data.kind = "wakeup"`):
 *      No notification shown. The service simply kicks the realtime
 *      gateway so the killed-app case gets a fresh WebSocket session
 *      and starts receiving subsequent events normally.
 *
 *  - **incoming emergency** (`data.kind = "emergency.alert"`):
 *      High-priority notification + post a [PushBus] event so an active
 *      `UserDashboardInteractor` (if any) can immediately render the
 *      incoming-emergency overlay without waiting for the WS round-trip.
 *
 *  - **token refresh** ([onNewToken]):
 *      Forwarded to [PushBus.tokenSubject]. The app graph subscribes and
 *      calls `DeviceRepository.register(...)` to update the backend.
 *
 * The service references no `AppGraph` directly — that would create a
 * tight coupling and force eager construction. Instead it publishes onto
 * static `PushBus` subjects which the graph subscribes to lazily.
 */
class AmanahFirebaseMessagingService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        Log.i(TAG, "FCM token refreshed")
        PushBus.onTokenRefreshed(token)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        val kind = data["kind"]

        when (kind) {
            KIND_WAKEUP -> {
                // Silent push — wake the realtime gateway. The MainActivity may
                // be dead; the graph's lazy state machine re-attaches itself
                // when the next foreground transition happens. We just hint
                // that an event is queued server-side.
                PushBus.onWakeupRequested()
            }

            KIND_EMERGENCY_ALERT -> {
                postEmergencyNotification(
                    alertId   = data["alert_id"].orEmpty(),
                    title     = data["title"] ?: "Emergency Alert",
                    body      = data["body"]  ?: "A nearby member needs assistance",
                )
                PushBus.onIncomingAlert(
                    alertId    = data["alert_id"].orEmpty(),
                    victimLat  = data["lat"]?.toDoubleOrNull(),
                    victimLng  = data["lng"]?.toDoubleOrNull(),
                )
            }

            else -> {
                Log.w(TAG, "Unknown FCM kind: $kind")
            }
        }
    }

    private fun postEmergencyNotification(alertId: String, title: String, body: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_EMERGENCY,
                "Emergency alerts",
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = "Critical SOS broadcasts from nearby members."
                setShowBadge(true)
                enableVibration(true)
            }
            manager.createNotificationChannel(channel)
        }

        val launch = packageManager.getLaunchIntentForPackage(packageName)
            ?.apply { flags = Intent.FLAG_ACTIVITY_NEW_TASK }
        val pi = launch?.let {
            PendingIntent.getActivity(
                this, 0, it,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        }

        val notification = NotificationCompat.Builder(this, CHANNEL_EMERGENCY)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(true)
            .apply { if (pi != null) setContentIntent(pi) }
            .build()

        manager.notify(alertId.hashCode().or(1), notification)
    }

    private companion object {
        const val TAG                  = "AmanahFcm"
        const val CHANNEL_EMERGENCY    = "amanah_emergency"
        const val KIND_WAKEUP          = "wakeup"
        const val KIND_EMERGENCY_ALERT = "emergency.alert"
    }
}
