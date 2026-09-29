package com.amanah.feature.core.session

import android.content.Context
import java.util.UUID

/**
 * Persistent storage for the installation's device id.
 *
 * Deliberately separate from [SecureTokenStore]: the identity must **survive
 * sign-out** (so the same installation maps to the same server-side `Device`
 * row every time the user logs in) whereas tokens are wiped.
 */
interface DeviceIdStore {
    fun read(): String?
    fun write(id: String)
}

/** [DeviceIdStore] backed by app-private SharedPreferences. */
class SharedPreferencesDeviceIdStore(context: Context) : DeviceIdStore {
    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    override fun read(): String? = prefs.getString(KEY, null)

    // commit(), not apply(): the id must hit disk before it is ever sent to the
    // server, otherwise a crash right after first login would mint a second id.
    override fun write(id: String) {
        prefs.edit().putString(KEY, id).commit()
    }

    private companion object {
        const val PREFS_NAME = "amanah_device_identity"
        const val KEY = "device_uuid"
    }
}

/**
 * Stable, install-scoped device identity sent as `device_uuid` at login.
 *
 * Model
 * -----
 * A random (v4) UUID generated **once**, on first use after install, and then
 * read back from [DeviceIdStore] for the lifetime of the installation:
 *
 *  - stable across logins, logouts, app restarts and app updates;
 *  - new on reinstall / "clear data" (the old server-side device row simply goes
 *    stale and is retired by the backend's least-recently-seen eviction);
 *  - not derived from hardware identifiers (IMEI/serial are unavailable to apps
 *    since Android 10; `ANDROID_ID` is a resettable, cross-app-linkable
 *    identifier Play policy discourages for this purpose), needs no permission,
 *    and is not restored from cloud backup (`allowBackup=false`), so a restored
 *    device never clones another device's identity.
 *
 * The identity is an *anchor for push-token and session binding*, never a
 * credential: authorisation always comes from the JWT.
 */
class DeviceIdentity(
    private val store: DeviceIdStore,
    private val generate: () -> String = { UUID.randomUUID().toString() },
) {
    val deviceUuid: String by lazy {
        store.read()?.takeIf { it.isNotBlank() } ?: generate().also { store.write(it) }
    }
}
