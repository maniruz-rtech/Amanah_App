package com.amanah.feature.user.repository

import com.amanah.feature.core.network.ApiService
import com.amanah.feature.core.network.DeviceDto
import com.amanah.feature.core.network.DeviceRegistration
import com.amanah.feature.core.repository.Outcome
import com.amanah.feature.core.repository.apiCall

class DeviceRepository(
    private val api: ApiService,
) {
    /**
     * Register this device with the backend. Called on first launch after
     * sign-in and whenever the FCM token rotates.
     */
    suspend fun register(
        deviceUuid: String,
        pushToken: String?,
        appVersion: String? = null,
    ): Outcome<DeviceDto> = apiCall {
        api.registerDevice(
            DeviceRegistration(
                deviceUuid = deviceUuid,
                pushToken  = pushToken,
                appVersion = appVersion,
            )
        )
    }

    suspend fun revoke(deviceId: String): Outcome<Unit> = apiCall {
        api.revokeDevice(deviceId)
    }
}
