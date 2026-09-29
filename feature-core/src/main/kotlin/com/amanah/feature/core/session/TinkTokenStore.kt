package com.amanah.feature.core.session

import android.content.Context
import android.util.Base64
import android.util.Log
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.google.crypto.tink.Aead
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking

/**
 * [SecureTokenStore] backed by Tink AEAD + Jetpack DataStore.
 *
 * Encryption: AES-256-GCM via Tink, with the keyset wrapped by Android Keystore
 * (see [AppKeysetManager]). Each token blob carries its own random IV (Tink
 * handles this internally) and an associated-data tag tying the ciphertext to
 * its logical purpose (`amanah/access` vs `amanah/refresh`) — this prevents
 * field-swap attacks where an attacker with file access tries to substitute a
 * refresh-token ciphertext into the access-token slot.
 *
 * Persistence: ciphertext is Base64-encoded and stored in a DataStore
 * preferences file named `amanah_tokens`. Writes are atomic; reads are
 * suspending but we cache the decrypted access/refresh tokens in memory so
 * [accessToken] / [refreshToken] are O(1) on the hot path (OkHttp interceptors).
 *
 * Migration: on construction, if a legacy `amanah_secure_prefs` EncryptedShared-
 * Preferences file is detected, its tokens are read once, re-encrypted via Tink,
 * stored in DataStore, and the legacy file is deleted. The legacy code path is
 * tolerant to library absence — if security-crypto is no longer on the classpath
 * the migration silently no-ops (the user is forced to re-login, which is the
 * intended graceful-degradation behaviour).
 */
class TinkTokenStore(
    appContext: Context,
    private val keysetManager: AppKeysetManager,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO),
) : SecureTokenStore {

    private val dataStore: DataStore<Preferences> = appContext.tokensDataStore

    @Volatile private var cachedAccess: String? = null
    @Volatile private var cachedRefresh: String? = null

    init {
        // Eager initial load (blocking — runs once at app startup before any
        // interceptor is wired). DataStore's first() is a fast disk read.
        runCatching { runBlocking { loadFromDisk() } }
            .onFailure { Log.w(TAG, "initial load failed: $it") }

        // Best-effort migration from legacy EncryptedSharedPreferences.
        runCatching { migrateLegacy(appContext) }
            .onFailure { Log.w(TAG, "legacy migration failed (non-fatal): $it") }
    }

    // ── Public API ─────────────────────────────────────────────────────────────

    override fun save(accessToken: String, refreshToken: String) {
        cachedAccess  = accessToken
        cachedRefresh = refreshToken

        val aead = keysetManager.obtainAead()
        val accessBlob  = encryptForPurpose(aead, accessToken,  PURPOSE_ACCESS)
        val refreshBlob = encryptForPurpose(aead, refreshToken, PURPOSE_REFRESH)

        // DataStore.edit is asynchronous; the in-memory cache is the source of
        // truth for the interceptors until the disk write commits.
        scope.launch {
            dataStore.edit { prefs ->
                prefs[KEY_ACCESS]  = accessBlob
                prefs[KEY_REFRESH] = refreshBlob
            }
        }
    }

    override fun clear() {
        cachedAccess  = null
        cachedRefresh = null
        scope.launch {
            dataStore.edit { prefs ->
                prefs.remove(KEY_ACCESS)
                prefs.remove(KEY_REFRESH)
            }
        }
        // Rotate the keyset on logout so any forensic dump of the data
        // directory after the user signs out cannot be decrypted.
        keysetManager.rotate()
    }

    override fun accessToken(): String?  = cachedAccess
    override fun refreshToken(): String? = cachedRefresh

    // ── internals ──────────────────────────────────────────────────────────────

    private suspend fun loadFromDisk() {
        val prefs = dataStore.data.first()
        val accessBlob  = prefs[KEY_ACCESS]
        val refreshBlob = prefs[KEY_REFRESH]
        if (accessBlob == null && refreshBlob == null) return

        val aead = keysetManager.obtainAead()
        cachedAccess  = accessBlob?.let { decryptForPurpose(aead, it, PURPOSE_ACCESS) }
        cachedRefresh = refreshBlob?.let { decryptForPurpose(aead, it, PURPOSE_REFRESH) }
    }

    private fun encryptForPurpose(aead: Aead, plaintext: String, purpose: ByteArray): String {
        val ct = aead.encrypt(plaintext.encodeToByteArray(), purpose)
        return Base64.encodeToString(ct, Base64.NO_WRAP)
    }

    private fun decryptForPurpose(aead: Aead, blob: String, purpose: ByteArray): String? = try {
        val ct = Base64.decode(blob, Base64.NO_WRAP)
        aead.decrypt(ct, purpose).decodeToString()
    } catch (e: Exception) {
        Log.w(TAG, "decrypt failed — dropping token slot ($e)")
        null
    }

    // ── Legacy migration ──────────────────────────────────────────────────────

    /**
     * One-shot migration: read tokens from the legacy EncryptedSharedPreferences
     * file (if present) and re-encrypt via Tink. Removes the legacy file on
     * success. Failures are non-fatal — worst case the user re-logs in.
     *
     * Reflection is used to avoid a hard dependency on androidx.security:security-crypto
     * which we're trying to remove from the classpath.
     */
    private fun migrateLegacy(appContext: Context) {
        if (cachedAccess != null && cachedRefresh != null) return   // already migrated

        val legacyPrefs = try {
            // Reflection: only present if security-crypto is still on classpath.
            val masterKeyClass     = Class.forName("androidx.security.crypto.MasterKey")
            val builderClass       = Class.forName("androidx.security.crypto.MasterKey\$Builder")
            val keySchemeClass     = Class.forName("androidx.security.crypto.MasterKey\$KeyScheme")
            val ctor               = builderClass.getConstructor(Context::class.java)
            val builder            = ctor.newInstance(appContext)
            val aes256Gcm          = keySchemeClass.getField("AES256_GCM").get(null)
            builderClass.getMethod("setKeyScheme", keySchemeClass).invoke(builder, aes256Gcm)
            val masterKey          = builderClass.getMethod("build").invoke(builder)

            val espClass           = Class.forName("androidx.security.crypto.EncryptedSharedPreferences")
            val prefKeyEncScheme   = Class.forName("androidx.security.crypto.EncryptedSharedPreferences\$PrefKeyEncryptionScheme")
            val prefValEncScheme   = Class.forName("androidx.security.crypto.EncryptedSharedPreferences\$PrefValueEncryptionScheme")
            val keySiv             = prefKeyEncScheme.getField("AES256_SIV").get(null)
            val valGcm             = prefValEncScheme.getField("AES256_GCM").get(null)
            val createMethod       = espClass.getMethod(
                "create",
                Context::class.java, String::class.java, masterKeyClass, prefKeyEncScheme, prefValEncScheme,
            )
            createMethod.invoke(null, appContext, LEGACY_PREF_FILE, masterKey, keySiv, valGcm)
                as android.content.SharedPreferences
        } catch (_: ClassNotFoundException) {
            // security-crypto already removed — nothing to migrate.
            return
        } catch (e: Throwable) {
            Log.w(TAG, "legacy decryption unavailable: $e")
            return
        }

        val legacyAccess  = legacyPrefs.getString(LEGACY_KEY_ACCESS, null)
        val legacyRefresh = legacyPrefs.getString(LEGACY_KEY_REFRESH, null)
        if (legacyAccess == null && legacyRefresh == null) return

        if (legacyAccess != null && legacyRefresh != null) {
            save(legacyAccess, legacyRefresh)
        }

        // Delete the legacy file (and its underlying SharedPreferences XML).
        legacyPrefs.edit().clear().apply()
        appContext.deleteSharedPreferences(LEGACY_PREF_FILE)
        Log.i(TAG, "legacy ESP tokens migrated to Tink")
    }

    // ── Constants ─────────────────────────────────────────────────────────────

    private companion object {
        const val TAG = "TinkTokenStore"

        // Each token slot has its own associated-data tag to prevent field-swap.
        val PURPOSE_ACCESS  = "amanah/access/v1".encodeToByteArray()
        val PURPOSE_REFRESH = "amanah/refresh/v1".encodeToByteArray()

        val KEY_ACCESS  = stringPreferencesKey("access_blob")
        val KEY_REFRESH = stringPreferencesKey("refresh_blob")

        const val LEGACY_PREF_FILE    = "amanah_secure_prefs"
        const val LEGACY_KEY_ACCESS   = "access_token"
        const val LEGACY_KEY_REFRESH  = "refresh_token"
    }
}

private val Context.tokensDataStore by preferencesDataStore(name = "amanah_tokens")
