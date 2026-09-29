package com.amanah.feature.core.network

import com.google.gson.Gson
import com.google.gson.JsonParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

/** Pins the wire format the backend's `LoginRequest` (app/schemas/auth.py) requires. */
class LoginRequestTest {

    private val gson = Gson()

    @Test fun `login body carries device_uuid and platform`() {
        val json = JsonParser.parseString(
            gson.toJson(LoginRequest(username = "alice", password = "pw", deviceUuid = "install-1", appVersion = "2.0.0"))
        ).asJsonObject

        assertEquals("alice", json["username"].asString)
        assertEquals("pw", json["password"].asString)
        assertEquals("install-1", json["device_uuid"].asString)
        assertEquals("android", json["platform"].asString)
        assertEquals("2.0.0", json["app_version"].asString)
    }

    @Test fun `optional push token is omitted when unknown`() {
        val json = JsonParser.parseString(
            gson.toJson(LoginRequest(username = "a", password = "b", deviceUuid = "d"))
        ).asJsonObject
        assertFalse(json.has("push_token"))
        assertFalse(json.has("app_version"))
    }

    @Test fun `device registration uses the backend field names`() {
        val json = JsonParser.parseString(
            gson.toJson(DeviceRegistration(deviceUuid = "d", pushToken = "tok"))
        ).asJsonObject
        assertEquals("tok", json["push_token"].asString)
        assertEquals("android", json["platform"].asString)
        assertFalse(json.has("fcm_token"))
    }
}
