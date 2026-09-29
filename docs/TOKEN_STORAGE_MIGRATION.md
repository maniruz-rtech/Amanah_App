# Token Storage Migration — EncryptedSharedPreferences → Tink + DataStore

## Why migrate

`androidx.security:security-crypto` (Jetpack Security) reached `1.1.0-alpha06` in 2022 and has been **deprecated by Google** with no GA replacement. We need:

1. A supported AEAD library (Tink — same team that built Jetpack Security under the hood).
2. A storage layer that survives OEM SharedPreferences quirks (Jetpack DataStore — atomic, file-backed, with explicit IPC semantics on Android 7+).

## Components introduced

| File | Purpose |
|---|---|
| `feature-core/session/SecureTokenStore.kt` | Public interface — every caller depends on this, never on the concrete impl. |
| `feature-core/session/AppKeysetManager.kt` | Wraps Tink `AndroidKeysetManager`. Keyset is generated on first launch and master-wrapped by Android Keystore (`android-keystore://amanah_master_key`). |
| `feature-core/session/TinkTokenStore.kt` | `SecureTokenStore` implementation: encrypts JWT/refresh tokens with Tink AEAD; persists Base64 ciphertext in DataStore Preferences (`amanah_tokens`). |

## Encryption properties

- **Algorithm:** AES-256-GCM via Tink `KeyTemplates.get("AES256_GCM")`.
- **IV:** generated per call by Tink (12-byte random nonce embedded in the ciphertext header).
- **Associated data:** tag binding each blob to its logical slot:
  - access-token blob → `"amanah/access/v1"`
  - refresh-token blob → `"amanah/refresh/v1"`

  This prevents a *field-swap* attack: an attacker with raw access to the preferences file cannot copy the refresh-token ciphertext into the access-token slot and have it decrypt — Tink's AEAD MAC includes the associated data.

- **Master key wrapping:** the keyset is wrapped by `android-keystore://amanah_master_key`. On modern Android the underlying private key is held in the TEE / StrongBox; the raw key bytes never enter app memory.

## Edge cases handled

| Scenario | Detection | Recovery |
|---|---|---|
| First launch (no keyset) | `AndroidKeysetManager` returns "no keyset"; Tink generates one. | Normal path. |
| Keystore loss (factory reset + restore, OEM bug, app cloning) | `obtainAead()` runs a probe encrypt/decrypt cycle on every load; failure triggers regeneration. | Keyset is regenerated; existing ciphertext is now undecryptable. User is silently signed out (token cache returns `null`); next launch routes to login. **This is intentional** — token loss must mean forced re-auth, never silent plaintext fallback. |
| App data backup / restore across devices | Same as keystore loss — the wrapped keyset's wrapping key vanishes. | Same — forced re-login. |
| Tink schema version bump | Tink handles upgrades internally; our associated-data tag is versioned (`/v1`) so we can change scheme without losing prior data. | Backward-compatible. |
| Concurrent `save` / `accessToken()` | In-memory cache fields are `@Volatile`; reads are O(1); writes happen on a coroutine on `Dispatchers.IO`. | Race-free for the read path. |

## Legacy ESP migration

On first instantiation, `TinkTokenStore` looks for the old `amanah_secure_prefs` SharedPreferences file. If present:

1. Tokens are read using reflection against `androidx.security.crypto.*` — this avoids a hard compile-time dependency on the library so we can remove it from `MODULE.bazel` once migration has shipped.
2. Tokens are re-encrypted via Tink and written to the new DataStore file.
3. The legacy SharedPreferences file is cleared and deleted.

If the legacy library is no longer on the classpath, migration silently no-ops. The user must re-login once — acceptable graceful-degradation behaviour.

## Cleanup at logout

`TinkTokenStore.clear()`:

1. Drops the in-memory access/refresh caches.
2. Removes the ciphertext blobs from DataStore.
3. **Rotates the Tink keyset** (`AppKeysetManager.rotate()`) so any forensic recovery of the data directory after sign-out cannot decrypt.

The next sign-in generates a fresh keyset wrapped by a fresh Keystore alias.

## Threat-model summary

| Attacker capability | Outcome |
|---|---|
| Reads `/data/data/com.amanah.app/...` on a rooted device | Sees Base64 ciphertext + wrapped keyset. Cannot decrypt without the device's Keystore. |
| Copies the data directory to another device (app cloning, OEM backup) | Wrapped keyset is bound to the *original* Keystore; decryption fails. Forced re-login. |
| Process memory dump while app is running | Sees the decrypted token in `cachedAccess` / `cachedRefresh`. Mitigation: rotate frequently (short JWT TTL), clear on logout, optional biometric prompt before access (future). |
| Field-swap (refresh blob into access slot) | AEAD associated-data tag mismatch → decrypt returns null → forced re-login. |

## Migration validation checklist

After deploying the new build to internal testers:

- [ ] Fresh-install path: token saved → kill app → relaunch → still signed in.
- [ ] Update-over-old-build path: previous tokens present in ESP → first launch of new build migrates → ESP file deleted (`ls /data/data/com.amanah.app/shared_prefs` shows no `amanah_secure_prefs.xml`).
- [ ] Logout → file system inspection: DataStore file present but empty; keyset removed.
- [ ] `accessToken()` measured latency p99 < 1 ms on a Pixel 7 (cache hit).
- [ ] Wipe Keystore (`KeyStore.getInstance("AndroidKeyStore").deleteEntry("amanah_master_key")`) → relaunch → app correctly falls back to login (no crash).

## Operational notes

- DataStore writes are *asynchronous*. The in-memory cache is the source of truth for the request hot path. Tests that hammer `save()` then kill the process should expect the on-disk state to lag the cache by up to a few milliseconds.
- `runBlocking { dataStore.data.first() }` runs once at construction. If the app cold-starts under disk-pressure this may take double-digit milliseconds — acceptable because it happens before `MainActivity.onCreate` finishes.
- The legacy migration code is best-effort. If you ever see a Sentry breadcrumb saying `legacy migration failed`, the user just re-logs in — not a P1.
