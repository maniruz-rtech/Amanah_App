package com.amanah.feature.emergency.repository

import com.amanah.feature.core.network.ApiService
import com.amanah.feature.core.network.IncidentDto
import com.amanah.feature.core.repository.Outcome
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response
import java.io.IOException

class EmergencyRepositoryTest {

    private val sampleIncident = IncidentDto(
        id           = "inc_test",
        status       = "broadcasting",
        severity     = "high",
        incidentType = "sos",
        startedAt    = "2026-05-22T00:00:00Z",
        resolvedAt   = null,
        canceledAt   = null,
        h3Cell       = "872bedfd5ffffff",
    )

    private fun httpException(code: Int): HttpException {
        val body = "{}".toResponseBody("application/json".toMediaType())
        return HttpException(Response.error<Any>(code, body))
    }

    // ── createSos ──────────────────────────────────────────────────────────────

    @Test fun `createSos returns Success when API returns 201`() = runTest {
        val api = mockk<ApiService>()
        coEvery { api.createSos(any()) } returns sampleIncident
        val repo = EmergencyRepository(api)

        val outcome = repo.createSos(lat = 23.81, lng = 90.41)

        assertTrue(outcome is Outcome.Success)
        assertEquals("inc_test", (outcome as Outcome.Success).value.id)
        coVerify(exactly = 1) { api.createSos(any()) }
    }

    @Test fun `createSos retries on transient NetworkDown then succeeds`() = runTest {
        val api = mockk<ApiService>()
        coEvery { api.createSos(any()) } throws IOException("boom") andThen sampleIncident
        val repo = EmergencyRepository(api)

        val outcome = repo.createSos(lat = 23.81, lng = 90.41)

        assertTrue(outcome is Outcome.Success)
        coVerify(exactly = 2) { api.createSos(any()) }
    }

    @Test fun `createSos surrenders to NetworkDown after 4 attempts`() = runTest {
        val api = mockk<ApiService>()
        coEvery { api.createSos(any()) } throws IOException("nope")
        val repo = EmergencyRepository(api)

        val outcome = repo.createSos(lat = 23.81, lng = 90.41)

        assertEquals(Outcome.NetworkDown, outcome)
        coVerify(exactly = 4) { api.createSos(any()) }
    }

    @Test fun `createSos short-circuits on 401 AuthFailed`() = runTest {
        val api = mockk<ApiService>()
        coEvery { api.createSos(any()) } throws httpException(401)
        val repo = EmergencyRepository(api)

        val outcome = repo.createSos(lat = 23.81, lng = 90.41)

        assertEquals(Outcome.AuthFailed, outcome)
        coVerify(exactly = 1) { api.createSos(any()) }
    }

    @Test fun `createSos surfaces 400-class server errors without retry`() = runTest {
        val api = mockk<ApiService>()
        coEvery { api.createSos(any()) } throws httpException(422)
        val repo = EmergencyRepository(api)

        val outcome = repo.createSos(lat = 23.81, lng = 90.41)

        assertTrue(outcome is Outcome.ServerError)
        assertEquals(422, (outcome as Outcome.ServerError).code)
        coVerify(exactly = 1) { api.createSos(any()) }
    }

    @Test fun `createSos retries on 500 server errors then succeeds`() = runTest {
        val api = mockk<ApiService>()
        coEvery { api.createSos(any()) } throws httpException(503) andThen sampleIncident
        val repo = EmergencyRepository(api)

        val outcome = repo.createSos(lat = 23.81, lng = 90.41)

        assertTrue(outcome is Outcome.Success)
        coVerify(exactly = 2) { api.createSos(any()) }
    }

    // ── cancel / resolve are simple wrappers — minimal verification ─────────────

    @Test fun `cancel passes reason through to ApiService`() = runTest {
        val api = mockk<ApiService>()
        coEvery { api.cancelIncident(any(), any()) } returns sampleIncident
        val repo = EmergencyRepository(api)

        val outcome = repo.cancel("inc_test", reason = "user_cancelled")

        assertTrue(outcome is Outcome.Success)
        coVerify { api.cancelIncident("inc_test", match { it.reason == "user_cancelled" }) }
    }
}
