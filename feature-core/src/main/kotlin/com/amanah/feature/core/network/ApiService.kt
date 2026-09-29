package com.amanah.feature.core.network

import com.google.gson.annotations.SerializedName
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.PATCH
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Single Retrofit interface for every HTTP call.
 *
 * Endpoints mirror the amanah18 FastAPI surface — keep field names matching
 * the server response (snake_case) via [SerializedName] aliases.
 */
interface ApiService {

    // ── Auth ──────────────────────────────────────────────────────────────────

    @POST("api/v1/auth/login")
    suspend fun login(@Body request: LoginRequest): LoginResponse

    @POST("api/v1/auth/refresh")
    suspend fun refresh(@Body request: RefreshRequest): TokenResponse

    @POST("api/v1/auth/logout")
    suspend fun logout(@Body request: LogoutRequest, @Header("Authorization") bearer: String)

    @POST("api/v1/auth/password-reset/request")
    suspend fun requestPasswordReset(@Body request: PasswordResetRequest)

    // ── OTP ───────────────────────────────────────────────────────────────────

    @POST("api/v1/otp/request")
    suspend fun otpRequest(@Body request: OtpRequestPayload): OtpRequestResponse

    @POST("api/v1/otp/verify")
    suspend fun otpVerify(@Body request: OtpVerifyPayload): OtpVerifyResponse

    @POST("api/v1/otp/resend")
    suspend fun otpResend(@Body request: OtpResendPayload): OtpRequestResponse

    // ── Users ─────────────────────────────────────────────────────────────────

    @GET("api/v1/users/me")
    suspend fun me(): UserProfileDto

    @PATCH("api/v1/users/me")
    suspend fun updateMe(@Body request: UpdateProfileRequest): UserProfileDto

    @POST("api/v1/users/devices")
    suspend fun registerDevice(@Body device: DeviceRegistration): DeviceDto

    @DELETE("api/v1/users/devices/{deviceId}")
    suspend fun revokeDevice(@Path("deviceId") deviceId: String)

    @GET("api/v1/users/trusted-contacts")
    suspend fun listTrustedContacts(): List<TrustedContactDto>

    @POST("api/v1/users/me/presence")
    suspend fun pingPresence(@Body request: PresencePingPayload)

    @GET("api/v1/users/nearby")
    suspend fun listNearby(
        @Query("cells") cells: String,
        @Query("max_idle_seconds") maxIdleSeconds: Int = 600,
        @Query("limit") limit: Int = 50,
    ): NearbyUsersDto

    // ── Responders ────────────────────────────────────────────────────────────

    @GET("api/v1/responders/availability")
    suspend fun getResponderAvailability(): AvailabilityDto

    @retrofit2.http.PUT("api/v1/responders/availability")
    suspend fun setResponderAvailability(@Body req: AvailabilityUpdateRequest): AvailabilityDto

    @POST("api/v1/responders/incidents/{id}/accept")
    suspend fun responderAccept(@Path("id") id: String, @Body req: ResponderAcceptRequest): IncidentDto

    @POST("api/v1/responders/incidents/{id}/decline")
    suspend fun responderDecline(@Path("id") id: String, @Body req: ResponderDeclineRequest): IncidentDto

    @POST("api/v1/responders/incidents/{id}/en-route")
    suspend fun responderEnRoute(@Path("id") id: String, @Body req: ResponderEnRouteRequest): IncidentDto

    @POST("api/v1/responders/incidents/{id}/arrived")
    suspend fun responderArrived(@Path("id") id: String): IncidentDto

    // ── Incidents ─────────────────────────────────────────────────────────────

    @POST("api/v1/incidents/sos")
    suspend fun createSos(@Body request: SosRequest): IncidentDto

    @GET("api/v1/incidents/{id}")
    suspend fun getIncident(@Path("id") id: String): IncidentDto

    @GET("api/v1/incidents/my/active")
    suspend fun myActiveIncidents(): List<IncidentDto>

    @POST("api/v1/incidents/{id}/location")
    suspend fun pushLocation(@Path("id") id: String, @Body update: LocationUpdate)

    @POST("api/v1/incidents/{id}/cancel")
    suspend fun cancelIncident(@Path("id") id: String, @Body request: CancelRequest): IncidentDto

    @POST("api/v1/incidents/{id}/resolve")
    suspend fun resolveIncident(@Path("id") id: String, @Body request: ResolveRequest): IncidentDto

    // ── Notifications ─────────────────────────────────────────────────────────

    @GET("api/v1/notifications")
    suspend fun listNotifications(@Query("skip") skip: Int = 0, @Query("limit") limit: Int = 50): PaginatedResponse<NotificationDto>

    @POST("api/v1/notifications/mark-read")
    suspend fun markRead(@Body request: MarkReadRequest)

    @POST("api/v1/notifications/mark-all-read")
    suspend fun markAllRead()

    @GET("api/v1/notifications/unread-count")
    suspend fun unreadCount(): UnreadCountResponse

    // ── Admin ─────────────────────────────────────────────────────────────────

    @GET("api/v1/admin/users")
    suspend fun adminListUsers(@Query("skip") skip: Int = 0, @Query("limit") limit: Int = 50): PaginatedResponse<UserProfileDto>

    @GET("api/v1/admin/users/{id}")
    suspend fun adminGetUser(@Path("id") id: String): UserProfileDto

    @POST("api/v1/admin/users/{id}/approve")
    suspend fun adminApproveUser(@Path("id") id: String)

    @POST("api/v1/admin/users/{id}/suspend")
    suspend fun adminSuspendUser(@Path("id") id: String, @Body request: SuspendRequest)

    @GET("api/v1/admin/audit-logs")
    suspend fun adminListAuditLogs(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 100,
    ): PaginatedResponse<AuditLogDto>

    @GET("api/v1/admin/approvals")
    suspend fun adminListApprovals(
        @Query("skip") skip: Int = 0,
        @Query("limit") limit: Int = 100,
    ): PaginatedResponse<ApprovalDto>
}

// ── Wire models ────────────────────────────────────────────────────────────────

/**
 * `device_uuid` and `platform` are **required** by the backend (`LoginRequest` in
 * `app/schemas/auth.py`); the server registers/refreshes the device during login and
 * binds the issued tokens to it. `device_uuid` must come from
 * [com.amanah.feature.core.session.DeviceIdentity] (stable per installation).
 */
data class LoginRequest(
    @SerializedName("username")    val username: String,
    @SerializedName("password")    val password: String,
    @SerializedName("device_uuid") val deviceUuid: String,
    @SerializedName("platform")    val platform: String = PLATFORM_ANDROID,
    @SerializedName("push_token")  val pushToken: String? = null,
    @SerializedName("app_version") val appVersion: String? = null,
) {
    companion object {
        const val PLATFORM_ANDROID = "android"
    }
}

data class LoginResponse(
    @SerializedName("access_token")  val accessToken: String,
    @SerializedName("refresh_token") val refreshToken: String,
    @SerializedName("token_type")    val tokenType: String,
    @SerializedName("expires_in")    val expiresIn: Int,
    @SerializedName("user")          val user: UserProfileDto,
    @SerializedName("mfa_required")  val mfaRequired: Boolean = false,
)

data class RefreshRequest(@SerializedName("refresh_token") val refreshToken: String)

data class TokenResponse(
    @SerializedName("access_token")  val accessToken: String,
    @SerializedName("refresh_token") val refreshToken: String,
    @SerializedName("token_type")    val tokenType: String,
    @SerializedName("expires_in")    val expiresIn: Int,
)

data class LogoutRequest(@SerializedName("refresh_token") val refreshToken: String)

data class PasswordResetRequest(
    @SerializedName("username_or_email") val usernameOrEmail: String,
)

data class UserProfileDto(
    @SerializedName("id")           val id: String,
    @SerializedName("username")     val username: String,
    @SerializedName("display_name") val displayName: String?,
    @SerializedName("email")        val email: String?,
    @SerializedName("phone")        val phone: String?,
    @SerializedName("roles")        val roles: List<String> = emptyList(),
    @SerializedName("is_active")    val isActive: Boolean = true,
    @SerializedName("is_verified")  val isVerified: Boolean = false,
    @SerializedName("is_suspended") val isSuspended: Boolean = false,
    @SerializedName("organization_id") val organizationId: String?,
    @SerializedName("region_id")    val regionId: String?,
)

data class UpdateProfileRequest(
    @SerializedName("display_name") val displayName: String? = null,
    @SerializedName("email")        val email: String? = null,
    @SerializedName("phone")        val phone: String? = null,
)

data class DeviceRegistration(
    @SerializedName("device_uuid")  val deviceUuid: String,
    @SerializedName("push_token")   val pushToken: String?,
    @SerializedName("platform")     val platform: String = LoginRequest.PLATFORM_ANDROID,
    @SerializedName("app_version")  val appVersion: String? = null,
)

data class DeviceDto(
    @SerializedName("id")           val id: String,
    @SerializedName("device_uuid")  val deviceUuid: String,
    @SerializedName("platform")     val platform: String,
)

data class TrustedContactDto(
    @SerializedName("id")           val id: String,
    @SerializedName("display_name") val displayName: String,
    @SerializedName("phone")        val phone: String?,
    @SerializedName("email")        val email: String?,
)

data class PresencePingPayload(
    @SerializedName("h3_cell_district") val h3CellDistrict: String,
    @SerializedName("h3_cell_block")    val h3CellBlock: String? = null,
)

data class NearbyUserDto(
    @SerializedName("user_id")          val userId: String,
    @SerializedName("display_name")     val displayName: String,
    @SerializedName("h3_cell_district") val h3CellDistrict: String,
    @SerializedName("last_seen_at")     val lastSeenAt: String,
    @SerializedName("is_responder")     val isResponder: Boolean = false,
)

data class NearbyUsersDto(
    @SerializedName("items")            val items: List<NearbyUserDto>,
    @SerializedName("total")            val total: Int,
    @SerializedName("queried_h3_cells") val queriedH3Cells: List<String>,
)

// ── Responder coordination ──────────────────────────────────────────────────

data class AvailabilityDto(
    @SerializedName("is_available")           val isAvailable: Boolean,
    @SerializedName("active_incident_count")  val activeIncidentCount: Int = 0,
    @SerializedName("last_location_at")       val lastLocationAt: String? = null,
)

data class AvailabilityUpdateRequest(
    @SerializedName("is_available") val isAvailable: Boolean,
    @SerializedName("lat")          val lat: Double? = null,
    @SerializedName("lng")          val lng: Double? = null,
    @SerializedName("battery_level") val batteryLevel: Int? = null,
)

data class ResponderAcceptRequest(
    @SerializedName("eta_minutes") val etaMinutes: Int,
)

data class ResponderDeclineRequest(
    @SerializedName("reason") val reason: String,
)

data class ResponderEnRouteRequest(
    @SerializedName("lat") val lat: Double,
    @SerializedName("lng") val lng: Double,
    @SerializedName("eta_seconds") val etaSeconds: Int? = null,
)

data class SosRequest(
    @SerializedName("lat")           val lat: Double,
    @SerializedName("lng")           val lng: Double,
    @SerializedName("accuracy_m")    val accuracyMeters: Int? = null,
    @SerializedName("h3_cell")       val h3Cell: String? = null,
    @SerializedName("incident_type") val incidentType: String = "SOS",
    @SerializedName("severity")      val severity: String = "HIGH",
    @SerializedName("silent_mode")   val silentMode: Boolean = false,
    @SerializedName("note")          val note: String? = null,
)

data class IncidentDto(
    @SerializedName("id")           val id: String,
    @SerializedName("status")       val status: String,
    @SerializedName("severity")     val severity: String,
    @SerializedName("incident_type") val incidentType: String,
    @SerializedName("started_at")   val startedAt: String,
    @SerializedName("resolved_at")  val resolvedAt: String?,
    @SerializedName("canceled_at")  val canceledAt: String?,
    @SerializedName("h3_cell")      val h3Cell: String?,
)

data class LocationUpdate(
    @SerializedName("lat")        val lat: Double,
    @SerializedName("lng")        val lng: Double,
    @SerializedName("accuracy_m") val accuracyMeters: Int?,
)

data class CancelRequest(
    @SerializedName("reason") val reason: String,
)

data class ResolveRequest(
    @SerializedName("note") val note: String?,
)

data class NotificationDto(
    @SerializedName("id")         val id: String,
    @SerializedName("type")       val type: String,
    @SerializedName("title")      val title: String,
    @SerializedName("body")       val body: String,
    @SerializedName("read")       val read: Boolean,
    @SerializedName("created_at") val createdAt: String,
)

data class MarkReadRequest(@SerializedName("notification_ids") val notificationIds: List<String>)

data class UnreadCountResponse(@SerializedName("count") val count: Int)

data class PaginatedResponse<T>(
    @SerializedName("items") val items: List<T>,
    @SerializedName("total") val total: Int,
    @SerializedName("skip")  val skip: Int,
    @SerializedName("limit") val limit: Int,
)

data class SuspendRequest(@SerializedName("reason") val reason: String)

// ── OTP ──────────────────────────────────────────────────────────────────────

data class OtpRequestPayload(
    @SerializedName("channel")   val channel: String,       // "sms" | "email"
    @SerializedName("purpose")   val purpose: String,       // "phone_verify" | "email_verify"
    @SerializedName("recipient") val recipient: String,
)

data class OtpRequestResponse(
    @SerializedName("otp_id")     val otpId: String,
    @SerializedName("expires_in") val expiresIn: Int,
)

data class OtpVerifyPayload(
    @SerializedName("otp_id") val otpId: String,
    @SerializedName("code")   val code: String,
)

data class OtpVerifyResponse(
    @SerializedName("verified") val verified: Boolean,
)

data class OtpResendPayload(
    @SerializedName("otp_id") val otpId: String,
)

// ── Admin ────────────────────────────────────────────────────────────────────

data class AuditLogDto(
    @SerializedName("id")            val id: String,
    @SerializedName("action")        val action: String,
    @SerializedName("resource_type") val resourceType: String?,
    @SerializedName("resource_id")   val resourceId: String?,
    @SerializedName("actor_user_id") val actorUserId: String?,
    @SerializedName("created_at")    val createdAt: String,
    @SerializedName("description")   val description: String?,
    @SerializedName("success")       val success: Boolean = true,
)

data class ApprovalDto(
    @SerializedName("id")           val id: String,
    @SerializedName("user_id")      val userId: String,
    @SerializedName("type")         val type: String,
    @SerializedName("status")       val status: String,
    @SerializedName("requested_at") val requestedAt: String,
)
