package com.amanah.feature.core.network

import okhttp3.CertificatePinner

/**
 * SPKI pin configuration for the Amanah HTTPS + WSS endpoints.
 *
 * **Production policy**:
 *   - At least 2 pins must be configured (primary + backup) so a single cert
 *     rotation cannot brick installed clients.
 *   - Pins are SPKI SHA-256 hashes, **not** full-cert fingerprints — SPKI hashes
 *     survive renewals of the same key.
 *   - The backup pin must be for a key currently held in cold storage / a
 *     separate HSM partition, ready to swap into the production cert when the
 *     primary rotates.
 *
 * **Failure mode**: if all current pins fail validation, OkHttp throws
 * `SSLPeerUnverifiedException` and the [com.amanah.feature.core.realtime.OkHttpRealtimeGateway]
 * terminates with [RealtimeConnectionState.TerminationReason.TLS_FAILED]. The
 * app shows a hard error — **we do not allow override**. This is mandatory for
 * an emergency-response system; silently falling back to unpinned TLS would let
 * a MITM intercept live location.
 *
 * **Rotation runbook**: see [docs/CERTIFICATE_PINNING_GUIDE.md](../../../../../../../../docs/CERTIFICATE_PINNING_GUIDE.md).
 *
 * **Debug builds**: by default pinning is disabled in debug builds (see
 * [forBuild]) so local development against self-signed certs works.
 */
object PinningConfig {

    /**
     * Pins for the production HTTPS / WSS hostname.
     *
     * Each entry has the form `sha256/<base64>`. Generate with:
     *
     *   openssl s_client -servername api.amanah.example -connect api.amanah.example:443 \
     *     < /dev/null 2>/dev/null \
     *     | openssl x509 -pubkey -noout \
     *     | openssl rsa -pubin -outform DER 2>/dev/null \
     *     | openssl dgst -sha256 -binary \
     *     | openssl enc -base64
     *
     * The placeholders below MUST be replaced before any production build.
     * Until they are replaced, [forBuild] will deliberately fail-closed in
     * release builds (see runtime check).
     */
    const val PRIMARY_PIN_HOSTNAME   = "api.amanah.example"
    const val PRIMARY_PIN            = "sha256/REPLACE_WITH_PRIMARY_SPKI_HASH_BEFORE_RELEASE"
    const val BACKUP_PIN             = "sha256/REPLACE_WITH_BACKUP_SPKI_HASH_BEFORE_RELEASE"

    /** Returns a pinner appropriate for the current build configuration. */
    fun forBuild(debugBuild: Boolean): CertificatePinner {
        if (debugBuild) return CertificatePinner.DEFAULT      // no-op (matches no host)

        check(PRIMARY_PIN.startsWith("sha256/") && !PRIMARY_PIN.contains("REPLACE_WITH")) {
            "PinningConfig.PRIMARY_PIN must be populated for release builds"
        }
        check(BACKUP_PIN.startsWith("sha256/") && !BACKUP_PIN.contains("REPLACE_WITH")) {
            "PinningConfig.BACKUP_PIN must be populated for release builds"
        }

        // Apply pins to the apex host AND any subdomain it may legitimately
        // serve (e.g. ws.api.amanah.example sharing the cert).
        return CertificatePinner.Builder()
            .add(PRIMARY_PIN_HOSTNAME,          PRIMARY_PIN, BACKUP_PIN)
            .add("*.$PRIMARY_PIN_HOSTNAME",     PRIMARY_PIN, BACKUP_PIN)
            .build()
    }
}
