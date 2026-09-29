package com.amanah.feature.auth.repository

import com.amanah.feature.core.network.ApiService
import com.amanah.feature.core.network.OtpRequestPayload
import com.amanah.feature.core.network.OtpRequestResponse
import com.amanah.feature.core.network.OtpResendPayload
import com.amanah.feature.core.network.OtpVerifyPayload
import com.amanah.feature.core.repository.Outcome
import com.amanah.feature.core.repository.apiCall

class OtpRepository(
    private val api: ApiService,
) {
    suspend fun request(
        channel: Channel,
        purpose: Purpose,
        recipient: String,
    ): Outcome<OtpRequestResponse> = apiCall {
        api.otpRequest(OtpRequestPayload(channel.wire, purpose.wire, recipient))
    }

    suspend fun verify(otpId: String, code: String): Outcome<Boolean> = apiCall {
        api.otpVerify(OtpVerifyPayload(otpId, code)).verified
    }

    suspend fun resend(otpId: String): Outcome<OtpRequestResponse> = apiCall {
        api.otpResend(OtpResendPayload(otpId))
    }

    enum class Channel(val wire: String) { SMS("sms"), EMAIL("email") }
    enum class Purpose(val wire: String) {
        PHONE_VERIFY("phone_verify"),
        EMAIL_VERIFY("email_verify"),
        PASSWORD_RESET("password_reset"),
    }
}
