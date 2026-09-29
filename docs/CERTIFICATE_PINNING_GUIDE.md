# Certificate Pinning Guide

## What we pin

**SPKI SHA-256 hashes**, not full-certificate fingerprints.

- A full-cert fingerprint changes every renewal — even when the same key is reused. SPKI-hash pins survive cert renewals as long as the key stays the same.
- Two pins are configured: **primary** (currently-used key) and **backup** (a key held in cold storage / separate HSM partition, ready to be put into rotation).

## Where pins are configured

`feature-core/src/main/kotlin/com/amanah/feature/core/network/PinningConfig.kt`

```
const val PRIMARY_PIN_HOSTNAME = "api.amanah.example"
const val PRIMARY_PIN          = "sha256/<base64-hash-of-primary-spki>"
const val BACKUP_PIN           = "sha256/<base64-hash-of-backup-spki>"
```

`PinningConfig.forBuild(debugBuild)` returns:

- `CertificatePinner.DEFAULT` (no-op) for `debugBuild = true`. This lets you point at `http://10.0.2.2:8000` or a self-signed dev server.
- A pinned `CertificatePinner` for release. **The build fails at runtime** if the constants still contain `REPLACE_WITH_...` — protecting against an accidental release without pins.

The same pinner is shared between the HTTPS Retrofit client (via `ApiFactory.create`) and the WebSocket client (via `ApiFactory.buildWsClient`).

## Extracting an SPKI hash

Two routes — pick whichever you trust more in your release process.

### From a live server

```bash
openssl s_client -servername api.amanah.example -connect api.amanah.example:443 </dev/null 2>/dev/null \
  | openssl x509 -pubkey -noout \
  | openssl rsa -pubin -outform DER 2>/dev/null \
  | openssl dgst -sha256 -binary \
  | openssl enc -base64
```

Prefix the output with `sha256/` and you have a pin value.

### From a PEM file

```bash
openssl x509 -in primary.pem -pubkey -noout \
  | openssl rsa -pubin -outform DER 2>/dev/null \
  | openssl dgst -sha256 -binary \
  | openssl enc -base64
```

(Replace `openssl rsa` with `openssl ec` if you're using ECDSA.)

## Rotation runbook

The whole point of having a backup pin is that you can rotate the production cert *without* shipping a new app. Standard playbook:

1. **Generate a fresh key + CSR** months before the active cert expires. Store the private key in cold storage.
2. **Compute the SPKI hash of the new key** with the command above.
3. **Ship an app release** that lists the new key's hash as the *backup* pin. Wait until the rollout reaches ≥ 95 % of the install base.
4. **Issue and deploy a server certificate that uses the new key.** TLS now serves a cert whose SPKI matches the *backup* pin in shipped clients — they still trust it because we listed both.
5. **Generate the next backup key** in cold storage, compute its hash.
6. **Ship another app release** that promotes the new key to *primary* and lists the *next* backup. Now the cycle continues.

You always have **two valid pins in flight** so a single stage of the rotation never bricks installed clients. If a key is compromised between stages 1 and 6, you skip the rollout wait and ship an emergency build with only the post-compromise key as pin.

## Failure handling

When pinning fails:

1. OkHttp throws `SSLPeerUnverifiedException`.
2. For HTTPS: the calling repository propagates the exception. The interceptor chain does NOT retry — pinning failure is treated as terminal.
3. For WSS: `OkHttpRealtimeGateway.onFailure` checks `t is SSLPeerUnverifiedException || SSLHandshakeException` and transitions to `Terminated(TLS_FAILED)`. No reconnect. The UI must show a hard error and **must not** allow the user to bypass.

We do **not** implement a "retry without pinning" fallback. Doing so would defeat the purpose. If pinning is firing in production for legitimate users, it's a misconfigured rotation — we ship a hotfix.

## Operational risks & mitigations

| Risk | Mitigation |
|---|---|
| Pin both keys → server uses a third cert by mistake → app lockout. | Backup pin lives in cold storage; staging server cycles through the rotation flow before prod. Add a pre-flight check in deploy CI that the prod cert SPKI matches one of the two pin values. |
| Two-pin window between rotations. | Acceptable — always at least 2 keys live so a compromise of one is recoverable. |
| Backup key compromise. | Treat as a key-loss incident; ship emergency release with new pins; consider revocation. |
| User has corporate MITM root CA installed. | Pin failure → user cannot connect. This is *correct*. We document this in the FAQ — emergency apps **must not** be MITMed. |
| Cert renewal with same key (RSA same modulus, new validity period). | No client action — SPKI is unchanged, pins still match. This is the common case. |

## Debug vs release configuration

| Build | Pinner | Effect |
|---|---|---|
| Debug | `CertificatePinner.DEFAULT` (no host matched) | All hosts pass pinning. Lets dev work against `http://10.0.2.2:8000` or self-signed servers. |
| Release | `CertificatePinner` with both pins | All connections to `api.amanah.example` (and `*.api.amanah.example`) must match one of the two pins or fail closed. |

## Validation checklist

Before shipping a release:

- [ ] `PRIMARY_PIN` and `BACKUP_PIN` are not the `REPLACE_WITH_...` placeholders (build will throw at first connection attempt otherwise).
- [ ] Both pins extracted by an out-of-band channel (production OpenSSL run + cold-storage HSM export) and committed via a signed commit.
- [ ] Staging server has been rotated through the pinning ceremony at least once in the last 90 days (verifies the rotation process works).
- [ ] `mitmproxy` ad-hoc test: redirect `api.amanah.example` to a mitmproxy instance with its own CA; verify the release build refuses to connect (Logcat shows `SSLPeerUnverifiedException`, gateway state machine moves to `Terminated(TLS_FAILED)`).
- [ ] Pre-flight CI script asserts the live server's SPKI matches one of the build-time pins.

## Pin-pinning anti-patterns to avoid

- ❌ Pinning the leaf certificate fingerprint (renews break the app).
- ❌ Pinning only one key (a single rotation bricks shipped builds).
- ❌ Implementing your own `X509TrustManager` that catches the exception and continues — kills the whole purpose.
- ❌ Forgetting subdomain wildcards (`*.api.amanah.example`) when the server later splits traffic onto subdomain hosts.
- ❌ Storing pins in a server-fetched config — defeats the purpose; if the server is compromised, the attacker rotates the pins too.
