package com.amanah.feature.admin.model

enum class AlertStatus { ACTIVE, RESOLVED, CANCELLED, TIMED_OUT }

data class AlertHistoryEntry(
    val alertId: String,
    val triggeredBy: String,        // userId
    val triggeredByName: String,
    val lat: Double,
    val lng: Double,
    val h3Cell: String,
    val status: AlertStatus,
    val triggeredAt: Long,
    val resolvedAt: Long? = null,
    val respondersNotified: Int = 0,
    val respondersAcknowledged: Int = 0,
)
