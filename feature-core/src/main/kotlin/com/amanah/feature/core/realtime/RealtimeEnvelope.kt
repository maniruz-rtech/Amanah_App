package com.amanah.feature.core.realtime

import com.google.gson.annotations.SerializedName

/**
 * Wire envelope for every realtime message — inbound or outbound.
 *
 * A single envelope shape replaces the per-channel models Scarlet used. The
 * server uses the same shape: `{ "v": 1, "type": "...", "event_id": "...", "ts": ..., "payload": {...} }`.
 *
 * Why a single envelope:
 *   - **Ordering** is established at the envelope layer (monotonic `ts` from
 *     the server) regardless of payload type.
 *   - **Deduplication** is by `event_id` — independent of payload semantics.
 *   - **Acknowledgement** is a generic envelope (`type = "ack"`) — the server
 *     does not need a per-channel ACK protocol.
 *
 * Payload is intentionally a raw [Map] — the gateway hands the payload to
 * feature-specific parsers (see [EventTypes]). This keeps the gateway agnostic
 * to feature evolution.
 */
data class RealtimeEnvelope(
    @SerializedName("v")        val version: Int = 1,
    @SerializedName("type")     val type: String,
    @SerializedName("event_id") val eventId: String,
    @SerializedName("ts")       val timestampMs: Long,
    @SerializedName("payload")  val payload: Map<String, Any?> = emptyMap(),

    /**
     * Optional client-supplied delivery deadline. Envelopes still queued at
     * this wall-clock time are dropped with [SendOutcome.Failed] and never
     * transmitted. Used for time-sensitive emergency broadcasts.
     */
    @SerializedName("ttl_ms")   val ttlMs: Long? = null,
)

/**
 * Sealed hierarchy of every inbound event after envelope decoding.
 *
 * The gateway's [RealtimeGateway.incoming] stream emits values of this type.
 * Adding a new event type is a compile-time fan-out:
 *   1. add a new sealed subclass here;
 *   2. add a branch in [com.amanah.feature.core.realtime.RealtimeEventParser];
 *   3. consumers fail closed on missing branches via Kotlin exhaustive `when`.
 */
sealed class RealtimeEvent {

    /** Server confirmed delivery of an outbound envelope. */
    data class Ack(val eventId: String) : RealtimeEvent()

    /** Heartbeat reply from the server. */
    data class Pong(val timestampMs: Long) : RealtimeEvent()

    /** Authentication finished — gateway moves to [RealtimeConnectionState.Online]. */
    object AuthAccepted : RealtimeEvent()

    /** Authentication rejected — gateway terminates with AUTH_REJECTED. */
    data class AuthRejected(val message: String) : RealtimeEvent()

    /** Emergency-alert broadcast: a victim's SOS reached this device. */
    data class EmergencyAlert(
        val alertId: String,
        val victimId: String,
        val lat: Double,
        val lng: Double,
        val h3Cell: String,
        val status: String,
        val kRing: Int,
        val serverTsMs: Long,
    ) : RealtimeEvent()

    /** Responder position update during an active emergency. */
    data class ResponderLocation(
        val responderId: String,
        val alertId: String,
        val lat: Double,
        val lng: Double,
        val etaSeconds: Int?,
        val serverTsMs: Long,
    ) : RealtimeEvent()

    /** Admin-channel notification (user approved/suspended, system message, etc.). */
    data class AdminNotification(
        val notificationType: String,
        val targetUserId: String?,
        val message: String,
        val serverTsMs: Long,
    ) : RealtimeEvent()

    /** Unknown envelope type — gateway logs and skips, but surfaces for diagnostics. */
    data class Unknown(val type: String, val raw: Map<String, Any?>) : RealtimeEvent()
}

/** Wire-format type discriminators. Stable identifiers — never rename. */
object EventTypes {
    const val PING              = "ping"
    const val PONG              = "pong"
    const val ACK               = "ack"
    const val AUTH_ACCEPTED     = "auth.accepted"
    const val AUTH_REJECTED     = "auth.rejected"
    const val EMERGENCY_ALERT   = "emergency.alert"
    const val RESPONDER_LOCATION = "responder.location"
    const val ADMIN_NOTIFICATION = "admin.notification"
    const val PRESENCE          = "presence"
}
