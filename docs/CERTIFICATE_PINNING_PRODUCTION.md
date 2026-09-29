# Certificate Pinning — Production Operations

## Overview

The Android client pins the SPKI SHA-256 of the production TLS endpoint.
A misconfigured pin **bricks installed clients** — they cannot reach the
backend, no UX surface can bypass this, and the only recovery is a new
app release. This document is the operational playbook for getting the
pinning right and rotating it safely.

## Extracting an SPKI hash

### From a live host

```bash
./scripts/extract_spki.sh api.amanah.example 443
# → sha256/<base64 of SHA-256(public-key-DER)>
```

### From a local PEM

```bash
./scripts/extract_spki.sh --pem ./prod-cert.pem
# → sha256/<base64>
```

Both modes produce the exact string format OkHttp's `CertificatePinner`
expects.

## The two pins

[feature-core/network/PinningConfig.kt](../feature-core/src/main/kotlin/com/amanah/feature/core/network/PinningConfig.kt) defines:

```kotlin
const val PRIMARY_PIN_HOSTNAME   = "api.amanah.example"
const val PRIMARY_PIN            = "sha256/REPLACE_…_BEFORE_RELEASE"
const val BACKUP_PIN             = "sha256/REPLACE_…_BEFORE_RELEASE"
```

`PinningConfig.forBuild(debugBuild)`:

- **Debug builds** → `CertificatePinner.DEFAULT` (no pins). Lets local
  dev work against `http://10.0.2.2:8000` or self-signed test servers.
- **Release builds** → builder pins primary + backup against
  `api.amanah.example` and `*.api.amanah.example`. Build fails-fast at
  runtime if either constant still contains `REPLACE_WITH_…`.

## Two pins, not one

A single pin = single point of failure: any cert rotation that doesn't
match it bricks the app. Two pins lets you:

1. Ship release N with `[primary=A, backup=B]`. Server uses cert A.
2. When A is approaching expiry: rotate the server to a cert backed by
   key B. Existing clients keep working because B is already pinned.
3. Ship release N+1 with `[primary=B, backup=C]`. New backup key C is in
   cold storage; the cycle continues.

**You always have two valid keys in flight.** A compromise of one is
recoverable without an emergency app release.

## Generating + storing pins for production

1. Generate keypair A in **cold storage** (HSM, KMS, or
   air-gapped machine). Issue cert A from your CA, deploy to staging.
2. Run `./scripts/extract_spki.sh <staging-host> 443` → record hash.
3. Generate keypair B in cold storage. Do NOT deploy yet. Run the SPKI
   extraction against the local PEM:

   ```bash
   ./scripts/extract_spki.sh --pem /secure/B.pem → record hash.
   ```
4. Update `PinningConfig.kt` with both hashes.
5. Run release build → verify with `mitmproxy` (see below).

## Pre-release verification (mitmproxy)

This is the single most important pre-release check. If the release build
silently accepts a wrong cert, the entire pinning chain is useless.

```bash
# 1. Start mitmproxy with its own CA
mitmproxy -p 8080 --mode reverse:https://api.amanah.example

# 2. Trust mitmproxy CA on a TEST device:
adb push ~/.mitmproxy/mitmproxy-ca-cert.pem /sdcard/
# Settings → Security → Install from storage

# 3. Force the test device to route api.amanah.example to mitmproxy
adb shell setprop dalvik.vm.dnsserver test.proxy

# 4. Install the RELEASE build
adb install -r bazel-bin/app/amanah.apk

# 5. Attempt login → expected:
#    - In logcat: SSLPeerUnverifiedException
#    - In gateway state: Terminated(TLS_FAILED)
#    - UI shows a hard error
```

If the login *succeeds* through mitmproxy: the pinning is misconfigured.
**Do not ship.**

## Rotation runbook

A standard cert rotation:

1. **T-30 days from expiry:** verify your two-pin schedule. The current
   release should have `[A, B]`. The next-key-in-cold-storage is C.
2. **T-14 days:** deploy a new server cert that uses key B (the
   already-pinned backup). The pinning still passes because B was
   pinned all along.
3. **T-7 days:** ship a release with `[B, C]`. Wait for ≥ 95 % rollout.
4. **T-0:** key A retired; old releases (still pinning A) won't connect
   but they're a tiny tail.
5. **T+0:** generate the next backup key D in cold storage. The cycle
   continues: `[B, C]` → `[C, D]` → ...

## Emergency rotation (key compromise)

If you discover a key has been compromised:

1. **Immediately** issue a new cert using the **other** pinned key.
   Deploy.
2. Ship an emergency app release with the compromised key removed and a
   new backup key added: `[uncompromised, new-cold]`.
3. Force-update: bump `versionCode` and use Play Console's
   in-app-updates "immediate" flow to require the new version.
4. Disclose per your incident-response policy.

## Failure mode

When pinning fails at runtime:

- **HTTPS path** (Retrofit calls): OkHttp throws
  `SSLPeerUnverifiedException`; the repository surfaces
  `Outcome.NetworkDown` (so the user sees "no network" rather than
  "MITM detected" — we don't expose attack details).
- **WSS path** (RealtimeGateway): the gateway's `onFailure` catches
  `SSLPeerUnverifiedException` or `SSLHandshakeException` and
  transitions to `Terminated(TLS_FAILED)`. **No reconnect.** This is
  intentional — a compromised pin should not loop the user through
  retries.

There is **no UX path** that lets the user bypass. The contract is:
if pinning fails, the app does not connect. Period.

## Operational checklist

Pre-release:

- [ ] `PinningConfig.PRIMARY_PIN` is not the `REPLACE_WITH_…` placeholder.
- [ ] `PinningConfig.BACKUP_PIN` is not the placeholder.
- [ ] Both hashes were extracted via `extract_spki.sh` and the output
      was committed without manual editing.
- [ ] A release APK was tested against mitmproxy and rejected the
      handshake.
- [ ] The same release APK successfully connects to the legitimate
      backend.
- [ ] The mapping file (`mapping.txt`) is uploaded to Sentry.

Post-release:

- [ ] Crash-free rate ≥ 99.5 % during the first 24h.
- [ ] Zero `SSLPeerUnverifiedException` crashes (other than test devices
      pointed at mitmproxy).
- [ ] Pin schedule documented in the team's secret-rotation calendar.
