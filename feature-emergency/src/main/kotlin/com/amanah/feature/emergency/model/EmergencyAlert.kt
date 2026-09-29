package com.amanah.feature.emergency.model

import com.google.gson.annotations.SerializedName

enum class EmergencyAlertStatus { ACTIVE, RESOLVED, CANCELLED, TIMED_OUT }

/**
 * Wire-format for the WebSocket emergency broadcast.
 *
 * The server transmits [lat]/[lng] as exact coordinates ONLY during
 * ACTIVE status. When status transitions to RESOLVED or CANCELLED the
 * server sends a follow-up message with noised or zeroed coordinates.
 * Clients MUST treat [lat]/[lng] as exact when [status] == ACTIVE and
 * as unsafe otherwise.
 */
data class EmergencyAlertMessage(
    @SerializedName("alertId")    val alertId: String,
    @SerializedName("victimId")   val victimId: String,
    @SerializedName("lat")        val lat: Double,
    @SerializedName("lng")        val lng: Double,
    @SerializedName("h3Cell")     val h3Cell: String,
    @SerializedName("status")     val status: EmergencyAlertStatus,
    @SerializedName("timestamp")  val timestamp: Long,
    @SerializedName("kRing")      val kRing: Int = 1,
)

data class ResponderLocationUpdate(
    @SerializedName("responderId") val responderId: String,
    @SerializedName("alertId")     val alertId: String,
    @SerializedName("lat")         val lat: Double,   // exact only during ACTIVE emergency
    @SerializedName("lng")         val lng: Double,
    @SerializedName("eta")         val etaSeconds: Int?,
    @SerializedName("timestamp")   val timestamp: Long,
)
