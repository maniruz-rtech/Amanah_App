package com.amanah.feature.core.session

import android.content.Context
import android.util.Log
import com.google.crypto.tink.Aead
import com.google.crypto.tink.KeyTemplates
import com.google.crypto.tink.KeysetHandle
import com.google.crypto.tink.aead.AeadConfig
import com.google.crypto.tink.integration.android.AndroidKeysetManager

/**
 * Wraps Tink's [AndroidKeysetManager] to provide a single AEAD primitive used
 * by [TinkTokenStore] to encrypt JWT tokens at rest.
 *
 * Key wrapping: the AEAD keyset itself is stored in SharedPreferences in the
 * default format Tink expects; the master key for the keyset is wrapped by the
 * **Android Keystore** (`AndroidKeystoreKmsClient`) so the raw key bytes never
 * leave the secure enclave / TEE on modern devices.
 *
 * Edge cases handled:
 *   - **First launch**: a new keyset is generated and wrapped.
 *   - **Keystore loss** (factory reset, OEM bug): the wrapper key vanishes; the
 *     stored keyset is then undecryptable. [obtainAead] detects this with a
 *     known-good probe, deletes the corrupt material, regenerates a keyset,
 *     and returns the new primitive. Existing ciphertext is unrecoverable
 *     (intended — we treat token-loss as forced re-login, not data exfiltration
 *     vector).
 *   - **Device restore** (cloud backup): the wrapped keyset may be restored
 *     onto a device whose Keystore can no longer unwrap it. Detected by the
 *     same probe.
 *
 * Thread-safety: [obtainAead] is idempotent and synchronized; safe to call
 * from any thread. The returned [Aead] instance is itself thread-safe.
 */
class AppKeysetManager(private val appContext: Context) {

    init {
        // AeadConfig must be registered once per process. Idempotent.
        AeadConfig.register()
    }

    @Volatile private var cached: Aead? = null
    private val lock = Any()

    fun obtainAead(): Aead {
        cached?.let { return it }
        synchronized(lock) {
            cached?.let { return it }

            val aead = try {
                buildAead()
                    .also { sanityCheck(it) }
            } catch (e: Exception) {
                Log.w(TAG, "Tink keyset unusable — regenerating ($e)")
                deleteKeyset()
                buildAead().also { sanityCheck(it) }
            }
            cached = aead
            return aead
        }
    }

    /**
     * Forget cached Aead and drop the keyset preferences file. The next
     * [obtainAead] call rebuilds from scratch.
     *
     * Used after logout to ensure no encrypted token blob remains decryptable.
     */
    fun rotate() {
        synchronized(lock) {
            cached = null
            deleteKeyset()
        }
    }

    // ── internals ──────────────────────────────────────────────────────────────

    private fun buildAead(): Aead {
        val handle: KeysetHandle = AndroidKeysetManager.Builder()
            .withSharedPref(appContext, KEYSET_NAME, PREF_FILE)
            .withKeyTemplate(KeyTemplates.get("AES256_GCM"))
            .withMasterKeyUri(MASTER_KEY_URI)
            .build()
            .keysetHandle
        return handle.getPrimitive(Aead::class.java)
    }

    /** Encrypts and decrypts a tiny payload to confirm the keyset is healthy. */
    private fun sanityCheck(aead: Aead) {
        val probe = "amanah-keyset-probe".encodeToByteArray()
        val ct = aead.encrypt(probe, ASSOCIATED_DATA)
        val pt = aead.decrypt(ct, ASSOCIATED_DATA)
        check(pt.contentEquals(probe)) { "Tink probe mismatch" }
    }

    private fun deleteKeyset() {
        appContext
            .getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
            .edit()
            .clear()
            .apply()
    }

    private companion object {
        const val TAG            = "AppKeysetManager"
        const val KEYSET_NAME    = "amanah_master_keyset"
        const val PREF_FILE      = "amanah_keyset_prefs"
        const val MASTER_KEY_URI = "android-keystore://amanah_master_key"
        val ASSOCIATED_DATA: ByteArray = "amanah/keyset-probe/v1".encodeToByteArray()
    }
}
