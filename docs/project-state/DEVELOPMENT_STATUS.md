# Development Status

_Snapshot 2026-09-27, after the data-model / login-contract pass._

## Traffic light
| Area | Status | Evidence |
|---|---|---|
| Android build | ✅ | `bazel build //app:amanah` (Bazel 8.8.1, Kotlin 2.4.20), APK 5.8 MB, targetSdk 36 |
| Android unit tests | ✅ 6/6 | `bazel test //...` (EventDedup, OutboundQueue, ReconnectStrategy, EmergencyRepository, DeviceIdentity, LoginRequest wire format) |
| Android login → `/users/me` (real app networking stack vs live backend) | ✅ | `//feature-core:LoginContractLiveTest` (opt-in, `manual`): login 200, tokens+profile parsed, `/users/me` 200 |
| Android on device/emulator | ❌ not possible here | no `/dev/kvm` |
| Backend tests | ✅ 178 passed, 0 failed/skipped | `pytest` on PostgreSQL 18.6 + PostGIS 3.6 |
| Migrations | ✅ | fresh → head, existing 007 DB with data → head, legacy "create_all + stamp" DB → head; `alembic check` clean; guarded by `tests/test_migrations.py` |
| Docker stack | ✅ | 5 services healthy; login + `/users/me` verified |

## Domain model decisions made
- **`users.status`** — persisted native enum `user_status_enum` (`pending_verification → pending_activation → active ⇄ suspended`, `active → deactivated`); the lifecycle state of record, filterable by admins. The booleans `is_active/is_verified/is_suspended` remain the per-request *enforcement* flags; the model keeps `status` in step when a flag is flipped (`@validates`), repository transitions set both, and 008 back-fills existing rows from the flags.
- **Device identity** — `devices` now match the API contract: `device_uuid` (install-scoped, `UNIQUE(user_id, device_uuid)`), `platform` (enum), `push_token`, `app_version`, `is_primary`, `last_seen_at`. Login registers/refreshes the device and binds the access + refresh tokens to `devices.id`; refresh rotation keeps the binding.
- **Android `device_uuid`** — a random v4 UUID generated once per installation and persisted in app-private storage that survives sign-out (`DeviceIdentity`); not ANDROID_ID/hardware-derived; new on reinstall by design.
- **`users.totp_secret_encrypted`** (AES-GCM) replaces the unused plaintext `mfa_secret`; **`users.created_by_id`** persists who created an account; contact lookup hashes are keyed HMACs.

## Next (suggested order)
1. Run the APK on a KVM-capable machine/device (KNOWN_ISSUES #1) — first real UI-level auth test.
2. Fix `/admin/users` 500 and align profile DTO / admin endpoints (KNOWN_ISSUES #5–7).
3. Wire Firebase (`google-services`), then register the push token after login.
4. Decide on the verification PIN (KNOWN_ISSUES #10) and rate limiting (#11).
5. `git init` + commit.
