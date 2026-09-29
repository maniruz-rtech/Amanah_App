# Known Issues

Verified 2026-09-27. Ordered by impact on "a real user can install, log in and use the app".
Status: **OPEN** unless noted. Nothing here is hidden by a skipped/xfail test — the backend suite is 178 passed / 0 skipped.

## Blockers for a usable product
1. **The APK has never been run on a device or emulator.** This machine has no `/dev/kvm`; the x86_64 AVD (`amanah`, android-35) refuses to start ("x86_64 emulation currently requires hardware acceleration"). Android login was verified with the app's *real* networking stack (ApiFactory/Retrofit/Gson/DeviceIdentity) against the live backend via `//feature-core:LoginContractLiveTest` — not through the UI. Needs a KVM-capable host or a physical device.
2. **FCM/push never initialises**: no `google-services.json` / Firebase init in the Bazel build. Consequences: no push token is ever produced; `NotificationService` now really sends via FCM but `FCM_ENABLED=false`, so notifications end `FAILED` (retried up to 3×). A push token that arrives *before* login is lost (registration needs auth) — re-register after login once Firebase is wired.
3. **Maps key is a placeholder** in `app/BUILD.bazel`; certificate-pin placeholders in `PinningConfig` make release builds fail closed (intended) until filled.
4. **No registration flow** (users are created by an admin / `create_admin.py`).
5. **`GET /api/v1/admin/users` → 500** (`MissingGreenlet`: `UserAdminResponse` reads a relationship that is not eager-loaded). Other admin list endpoints tested (`/admin/incidents`) work.

## Android ↔ backend contract gaps
6. Login response `user`: the app's `UserProfileDto` expects `display_name`, `email`, `phone`; the server sends `full_name`, `email_masked`, `phone_masked` → the app falls back to `username` for the display name and shows empty email/phone. Login itself works.
7. Admin screens call `GET /admin/users/{id}`, `POST /admin/users/{id}/approve`, `GET /admin/approvals` — none exist on the backend.
8. HTTP MFA contract is inconsistent: `LoginResponse` (`mfa_session_token`) vs `MFAChallengeResponse`/`MFAVerifyRequest` (`mfa_challenge_id`); the service layer is correct and tested, the Android app has no MFA UI. MFA sessions live in a process-local dict (`_mfa_sessions`), not Redis → break with >1 API worker.
9. `DeviceService.register_device` audit metadata `is_new` is always `True` (`device.id is not None`).

## Backend design gaps (not regressions)
10. **Incident verification PIN is not implemented.** `SOSCreateResponse.verification_pin` / `CancelIncidentRequest.verification_pin` exist in schemas and `generate_verification_pin()` exists, but nothing stores or checks a PIN and the Android client never sends one. The old tests that expected `create_sos` to return `(incident, pin)` were rewritten to the actual behaviour (`incident`); decide whether the PIN feature is wanted.
11. Rate limiting is configured (`rate_limit_*`) but no limiter is wired (slowapi was removed as unused). Login lockout by failed attempts does work.
12. `firebase-admin` (grpc, firestore) is only used for FCM but pulls heavy transitive dependencies (grpc, firestore) — candidate to replace with the FCM HTTP v1 API.
13. Two parallel device-registration services (`services/device.py`, `services/user.py`) and duplicate repository code; three WebSocket implementations (`websocket.py` mounted; `websocket_v2.py`, `api/v1/websocket.py`, `websockets/` unused or test-only). `TrustedContactLimitError` is reused for the device limit.
14. `users.phone_hash` / `email_hash` are now HMAC-SHA256 keyed by `ENCRYPTION_KEY` (`hash_contact`). Rows written before this change (e.g. by the old `create_admin.py`) hold plain SHA-256 values. Nothing reads these columns yet; if lookups by phone/email are added, re-hash existing rows first, and treat key rotation as requiring a re-hash.
15. Pydantic v2 class-`Config` deprecation warnings (14 in pytest) — harmless until Pydantic v3.

## Database / migrations
16. Migration **downgrades are intentionally partial** (008/009 remove what they added but do not narrow widened types or convert enum columns back to VARCHAR). Roll back by restoring a backup.
17. Migration 008 **aborts** if any `users.region_id IS NULL` (the model requires it) — assign a region first. 008 also fails loudly if a VARCHAR status/type column contains a value outside its enum.
18. Existing dev database (old `amanah_db` container, PG16, created by `init_schema_from_models.py` + `stamp`): dump/restore into PG18 (see `backend/docker-compose.yml` header), then `alembic upgrade head` — 008/009 are idempotent and converge it (covered by `test_legacy_create_all_and_stamp_database_converges`).
19. Device identity: reinstalling the app / clearing data creates a new `device_uuid` (by design); the old row goes stale and is retired only when the 10-device limit forces eviction of the stalest non-primary device.
20. Migration tests need a Postgres where the test user may `CREATE DATABASE` (they build and drop scratch DBs).

## Security / operations
21. `backend/.env` holds dev secrets (rotate before any shared use); `create_admin.py` still prompts with `admin123` as the default password.
22. `MODULE.bazel` `maven.install` needs `REPIN=1 bazel run @maven//:pin` after any artifact change (lock file is enforced).
23. Repository is not under git; the only rollback point is `amanah-baseline.tgz` in the Claude session scratchpad.
