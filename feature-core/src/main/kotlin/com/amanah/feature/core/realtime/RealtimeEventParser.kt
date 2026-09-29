package com.amanah.feature.core.realtime

/**
 * Converts a decoded [RealtimeEnvelope] into a typed [RealtimeEvent].
 *
 * Kept as a separate object so it can be unit-tested without spinning up the
 * gateway. Unknown `type` values become [RealtimeEvent.Unknown] rather than
 * throwing — the gateway logs and forwards them for diagnostics, but never
 * crashes on a server-side schema change.
 */
object RealtimeEventParser {

    fun parse(envelope: RealtimeEnvelope): RealtimeEvent = when (envelope.type) {
        EventTypes.PONG ->
            RealtimeEvent.Pong(envelope.timestampMs)

        EventTypes.ACK ->
            RealtimeEvent.Ack(eventId = envelope.payload.stringOr("event_id", envelope.eventId))

        EventTypes.AUTH_ACCEPTED ->
            RealtimeEvent.AuthAccepted

        EventTypes.AUTH_REJECTED ->
            RealtimeEvent.AuthRejected(message = envelope.payload.stringOr("message", "auth rejected"))

        EventTypes.EMERGENCY_ALERT -> RealtimeEvent.EmergencyAlert(
            alertId    = envelope.payload.stringOr("alert_id", envelope.eventId),
            victimId   = envelope.payload.stringOr("victim_id", ""),
            lat        = envelope.payload.doubleOr("lat", 0.0),
            lng        = envelope.payload.doubleOr("lng", 0.0),
            h3Cell     = envelope.payload.stringOr("h3_cell", ""),
            status     = envelope.payload.stringOr("status", "ACTIVE"),
            kRing      = envelope.payload.intOr("k_ring", 1),
            serverTsMs = envelope.timestampMs,
        )

        EventTypes.RESPONDER_LOCATION -> RealtimeEvent.ResponderLocation(
            responderId = envelope.payload.stringOr("responder_id", ""),
            alertId     = envelope.payload.stringOr("alert_id", ""),
            lat         = envelope.payload.doubleOr("lat", 0.0),
            lng         = envelope.payload.doubleOr("lng", 0.0),
            etaSeconds  = envelope.payload.intOrNull("eta_seconds"),
            serverTsMs  = envelope.timestampMs,
        )

        EventTypes.ADMIN_NOTIFICATION -> RealtimeEvent.AdminNotification(
            notificationType = envelope.payload.stringOr("type", "system"),
            targetUserId     = envelope.payload.stringOrNull("user_id"),
            message          = envelope.payload.stringOr("message", ""),
            serverTsMs       = envelope.timestampMs,
        )

        else -> RealtimeEvent.Unknown(type = envelope.type, raw = envelope.payload)
    }

    // ── Tolerant accessors ────────────────────────────────────────────────────

    private fun Map<String, Any?>.stringOr(key: String, default: String): String =
        (get(key) as? String) ?: default

    private fun Map<String, Any?>.stringOrNull(key: String): String? =
        (get(key) as? String)

    private fun Map<String, Any?>.doubleOr(key: String, default: Double): Double = when (val v = get(key)) {
        is Number -> v.toDouble()
        else      -> default
    }

    private fun Map<String, Any?>.intOr(key: String, default: Int): Int = when (val v = get(key)) {
        is Number -> v.toInt()
        else      -> default
    }

    private fun Map<String, Any?>.intOrNull(key: String): Int? = (get(key) as? Number)?.toInt()
}
