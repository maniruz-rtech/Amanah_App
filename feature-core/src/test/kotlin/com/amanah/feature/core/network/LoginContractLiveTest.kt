package com.amanah.feature.core.network

import com.amanah.feature.core.session.DeviceIdStore
import com.amanah.feature.core.session.DeviceIdentity
import com.amanah.feature.core.session.SecureTokenStore
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * LIVE contract test: the real Android `ApiFactory`/Retrofit/Gson stack against a
 * running backend. Opt-in (tagged `manual` in BUILD.bazel, so `bazel test //...`
 * does not run it):
 *
 *     bazel test //feature-core:LoginContractLiveTest \
 *         --test_env=AMANAH_LIVE_URL=http://localhost:8000 \
 *         --test_env=AMANAH_LIVE_USER=<username> --test_env=AMANAH_LIVE_PASSWORD=<password>
 *
 * Covers: fresh install identity -> POST /auth/login -> tokens+profile parsed by the
 * app's DTOs -> authenticated GET /users/me through the app's interceptor chain.
 */
class LoginContractLiveTest {

    private class MemoryTokens : SecureTokenStore {
        private var access: String? = null
        private var refresh: String? = null
        override fun save(accessToken: String, refreshToken: String) { access = accessToken; refresh = refreshToken }
        override fun clear() { access = null; refresh = null }
        override fun accessToken() = access
        override fun refreshToken() = refresh
    }

    private class MemoryIdStore : DeviceIdStore {
        var value: String? = null
        override fun read() = value
        override fun write(id: String) { value = id }
    }

    @Test fun `fresh install logs in and reads its profile`() = runBlocking {
        val url = System.getenv("AMANAH_LIVE_URL")
        val user = System.getenv("AMANAH_LIVE_USER")
        val password = System.getenv("AMANAH_LIVE_PASSWORD")
        assumeTrue("set AMANAH_LIVE_URL/USER/PASSWORD to run the live contract test", url != null && user != null && password != null)

        val tokens = MemoryTokens()
        val api = ApiFactory.create(baseUrl = url!!, tokenStore = tokens, debug = true, onSessionExpired = {})
        val identity = DeviceIdentity(MemoryIdStore())

        val login = api.login(
            LoginRequest(username = user!!, password = password!!, deviceUuid = identity.deviceUuid, appVersion = "live-test")
        )
        assertTrue(login.accessToken.isNotBlank())
        assertTrue(login.refreshToken.isNotBlank())
        assertEquals(user, login.user.username)

        tokens.save(login.accessToken, login.refreshToken)
        val me = api.me()
        assertEquals(login.user.id, me.id)
        assertEquals(user, me.username)
    }
}
