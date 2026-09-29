# Upgrade Log

Baseline snapshot (pre-upgrade sources, excluding Bazel symlinks): `amanah-baseline.tgz` in the Claude
session scratchpad — the repository is **not** under git, so this tarball is the only rollback point.
Recommended before anything else: `git init` and commit.

Format: Date · Component · Old → New · Reason · Files changed · Build result · Test result · Notes.

## 0. Known blocker (Android compile) — 2026-09-26
- **Component:** `feature-user`, `libraries/nodes-framework`, `app` (source fixes, no version change)
- **Old → New:** did not compile → compiles
- **Reason:** (a) `UserDashboardInteractor` used Reaktive `subscribe` without importing it; (b) `ResponderMapView` had a private `key(vararg)` wrapper that crashed the Compose compiler (`irJoinKeyChain: Empty collection can't be reduced`); (c) `AmanahApplication` used `BuildConfig.DEBUG`, which Bazel does not generate; (d) `AppGraph` FCM subscriptions missing `subscribe`/`launch` imports and used `GlobalScope`; (e) `Node.performAttach/performDetach` were `internal`, so `RootNode` (other module) could not call them.
- **Files:** `feature-user/.../UserDashboardInteractor.kt`, `feature-user/.../ResponderMapView.kt`, `app/.../AmanahApplication.kt` (uses `FLAG_DEBUGGABLE`), `app/.../di/AppGraph.kt` (process-lifetime `CoroutineScope` instead of `GlobalScope`), `libraries/nodes-framework/.../Node.kt` (now public).
- **Build:** Kotlin compiled; then failed in R8 (see group 1). **Test:** n/a.
- **Note:** the `autoDispose()` ambiguity noted in the audit did not materialise once `subscribe` was imported (the Reaktive/Rx overloads resolve by receiver type).

## 1. Build toolchain — 2026-09-26
- **Bazel** 7.4.1 → 8.8.1; **rules_android** 0.6.0 → 0.7.3; **rules_kotlin** 2.1.0 → 2.4.20; **rules_jvm_external** 6.3 → 7.1; **bazel_skylib** 1.7.1 → 1.9.2; **platforms** 0.0.10 → 1.1.0; **Kotlin** 2.1.0 → 2.4.20; **compileSdk/targetSdk** 35 → 36 (SDK platform-36 + build-tools 36.0.0 installed); JDK tools 11/17 → 21, Java level 17; Kotlin JVM target 1.8 → 17.
- **Reason:** see DEPENDENCY_VERSIONS.md §1. Under rules_android 0.6.0 R8 failed with missing `android.view.RenderNode` and every `androidx.*.R$id` (AAR resources not merged); 0.7.3 fixes that.
- **Files:** `.bazelversion`, `MODULE.bazel`, `.bazelrc` (JDK/Java flags, non-deprecated flag names), `BUILD.bazel` (`define_kt_toolchain` JVM 17), `WORKSPACE` (see Removed), `app/BUILD.bazel` (dropped removed `multidex` attribute, targetSdk 36), `app/proguard-rules.pro` (`-dontwarn` for androidx.window OEM extensions and Guava `ListenableFuture` — Gradle injects these from consumer rules, Bazel does not).
- **Build:** initially failed (`multidex` attr; Compose plugin 2.1.0 vs compiler 2.4.20; JVM-target inline error; R8 missing classes) — all fixed; final `bazel build //app:amanah` **succeeds** (APK 5.8 MB, targetSdk 36 confirmed with `aapt2 dump badging`). **Tests:** see group 2.

## 2. Android / Kotlin dependencies — 2026-09-26
- **Old → New:** see DEPENDENCY_VERSIONS.md §2 (Compose 1.7.5→1.12.1, Material3 1.3.1→1.4.0, AndroidX core/lifecycle/activity/datastore, OkHttp 4.12→5.5, Retrofit 2.11→3.0, Tink 1.13→1.23, Firebase, Maps, H3, Reaktive 2.3→2.4, coroutines 1.9→1.11, …).
- **Reason:** currency, security (Tink/OkHttp/Gson), and Compose 1.12 for Kotlin 2.4 compatibility. **No application source changes were needed** for these upgrades (all modules compiled as-is).
- **Files:** `MODULE.bazel` (artifact list; extra conflict pins: `activity`, `activity-ktx`, `core`, `collection-jvm`, `lifecycle-livedata-core`, `lifecycle-viewmodel-savedstate`, `savedstate(-android)`, `fragment`), `feature-core/BUILD.bazel` (datastore `-android`), `maven_install.json` (regenerated real lock file, replaces empty placeholder), `app/BUILD.bazel`, `feature-auth/BUILD.bazel`.
- **Build:** ✅ pinned-mode build passes. **Tests:** ✅ `bazel test //...` → 4/4 pass (see below).
- **Tests added:** Bazel `kt_android_local_test` targets for the 4 existing Kotlin test classes (they previously existed but were wired to nothing): `//feature-core:{EventDedupTest,InMemoryOutboundQueueTest,ReconnectStrategyTest}`, `//feature-emergency:EmergencyRepositoryTest`, plus `src/test/AndroidManifest.xml` (minSdk 26) in both modules.
- **Bug found by running the tests:** `EventDedup` claimed LRU eviction but used `containsKey`, which does not refresh access order in an access-ordered `LinkedHashMap`; replayed event IDs were evicted early. Fixed (`seen[eventId] != null`), test now passes.
- **Removed as verified-unused** (no imports anywhere in `app/`, `feature-*`, `libraries/`; build passes without them): `dagger`, `dagger-compiler` (DI is manual `AppGraph`), `error_prone_core` (javac bundled by the Bazel Java toolchain supplies `-Xplugin:ErrorProne`; no Java sources), `kotlinx-serialization-json`, `navigation-compose`, `androidx.biometric`, `androidx.appcompat` (theme is `android:Theme.Material`; `MainActivity : ComponentActivity`), `lifecycle-viewmodel-compose`, `maps-compose-utils`, `reaktive coroutines-interop`, `reaktive-testing`, `rxkotlin`, `tinder statemachine`.
- **Not verified on a device/emulator:** runtime behaviour (Compose 1.12 / Material3 1.4 visual changes, OkHttp 5 runtime, Tink keyset migration on an existing install). Compile + unit tests only.

## 3–4. Backend Python runtime & dependencies — 2026-09-26
- **Python:** 3.12 kept. **Deps:** see DEPENDENCY_VERSIONS.md §3 (FastAPI 0.109→0.141.1 with Starlette 1.7, Pydantic 2.6→2.13, SQLAlchemy 2.0.25→2.0.54, Celery 5.3→5.6.3, Alembic 1.13→1.20, firebase-admin 6→7.7, python-jose 3.3→3.5, …). `pip check` clean.
- **Files:** `backend/requirements.txt` (runtime only, direct pins), `backend/requirements-dev.txt` (new; test/lint), `backend/Makefile` (`install` uses dev file; broken `celery-flower` target removed), `backend/app/services/push.py` + `notification.py` (`send_multicast` → `send_each_for_multicast`; **the old call no longer exists in firebase-admin 7 and its `except Exception` would have silently swallowed emergency push failures**), `backend/app/db/models/user.py` (`full_name` setter so `User(full_name=…)` works), `backend/app/core/config.py` (see group 7).
- **Removed as verified-unused** (no import in `app/`, `migrations/`, `scripts/`, `create_admin.py`): `aioredis` (abandoned, merged into redis-py), `psycopg2-binary` (Alembic runs on the async engine), `gunicorn` (not referenced by Dockerfile/compose/Makefile), `qrcode[pil]` (no MFA QR code generated server-side), `python-multipart` (no `Form`/`File`/`UploadFile`), `passlib` (hashing uses `argon2` directly), `slowapi`, `sentry-sdk`, `prometheus-fastapi-instrumentator`, `python-dateutil` (only transitive), duplicate `httpx` entry. **Note:** rate-limit settings (`rate_limit_*`) exist in config but no limiter is wired — that is a pre-existing gap, not caused by this change.
- **Build/Import:** ✅ `import app.main` OK; app boots in Docker.
- **Test result:** see group 5.

## 5. Database / Redis / Celery + test infrastructure — 2026-09-26
- **PostgreSQL/PostGIS** 16-3.4 → 18-3.6 (PG 18.6, PostGIS 3.6.4); **Redis** 7 → 8.10.2; Celery 5.6.3.
- **Test infra restored:** new `backend/tests/conftest.py` (session engine on a real PostGIS DB, refuses any DB not named `*_test`, per-test rolled-back transaction, seeds `org_test`/`reg_test`), `pyproject.toml` (`asyncio_default_*_loop_scope = "session"` for pytest-asyncio 1.x), `backend/docker/initdb/01-test-database.sql` (creates `amanah_test` on first DB init).
- **Result:** baseline `35 passed / 127 errors` (fixtures missing) → **`47 passed / 13 failed / 102 errors`** on the upgraded stack. **The remaining 115 are genuine test-vs-code drift, not upgrade regressions, and were deliberately not hidden or skipped**: 97 errors `TypeError: 'status' is an invalid keyword argument for User` (the tests and `app/repositories/user.py`, `services/admin.py` expect a `User.status` column that the model does not have — the same defect appeared in `backend.log` in April as `'User' object has no attribute 'status'`), 9 × `'email'` invalid kwarg for `User`, 3 × `OTPPurpose.REGISTRATION` missing, 3 FK violations (`created_by_id`), 3 naive-vs-aware datetime errors.
- **Alembic:** ✅ `alembic upgrade head` (001→007) succeeds on a fresh PG18. Found and fixed: the migrations directory was named `alembic/` with an `__init__.py` and, with `PYTHONPATH=/app` in the image, **shadowed the `alembic` package** (`No module named 'alembic.config'`) → renamed to `migrations/` (`alembic.ini`, `pyproject.toml`, `.dockerignore`, `README.md` updated). `alembic check` still reports large model↔migration drift (e.g. `admin_approvals` table has no migration) — pre-existing, not fixed.
- **Celery functional fix:** the worker was started without `-Q`, so it consumed only the `default` queue while `task_routes` sends push/SMS/email/escalation tasks to `notifications`, `incidents`, `maintenance`, `sms`, `email` → those tasks would never run. Worker now consumes all six queues (verified in the worker startup banner).

## 6. Docker / infrastructure — 2026-09-26
- **Files:** `backend/docker-compose.yml`, `backend/Dockerfile`, `backend/docker/initdb/01-test-database.sql`.
- **Changes:** PG18-correct volume mount (`/var/lib/postgresql`), Redis `maxmemory 256mb` + `noeviction`, healthchecks that actually match each service (the old Dockerfile healthcheck curled port 8000 inside the Celery containers → permanently `unhealthy`), `curl` removed from the image (stdlib healthcheck on `/api/v1/live`), one shared `amanah-backend:dev` image for api/worker/beat (previously built 3×), beat schedule file moved to `/tmp` (it was being written into the source tree), DB/Redis/API ports bound to `127.0.0.1` and overridable, fixed `container_name`/network name removed (allows side-by-side stacks), Flower removed (was not installable from `requirements.txt`).
- **Verification:** ran the full stack under an isolated project name (`amanah_verify`, ports 15434/16380/18000, torn down with `down -v` afterwards): all 5 services **healthy**; `/api/v1/live` and `/api/v1/ready` OK; PG 18.6 + PostGIS 3.6.4; Redis 8.10.2; migrations OK; `create_admin.py` + `POST /auth/login` + `GET /users/me` = 200 (Argon2, JWT, AES-GCM, SQLAlchemy/asyncpg all working on the new stack). Idle memory: api 109 MB, worker 186 MB, beat 55 MB, PG 65 MB, Redis 6 MB.
- **The user's existing containers (`amanah_api`, `e889…_amanah_db` on 5434, etc.) were not touched** and still run the old 4-month-old images with PG16 data. Migrate with the dump/restore commands in the compose header.

## 7. Security / configuration — 2026-09-26
- `backend/app/core/config.py`: in `staging`/`production` the app now **refuses to start** with placeholder/short `JWT_SECRET_KEY`/`ENCRYPTION_KEY` or `DEBUG=true` (verified). DB pool defaults 20+20 → 10+10 per process (lower Postgres RAM/connections; env-tunable).
- `app/src/main/res/xml/network_security_config.xml` + manifest: cleartext denied globally, permitted only for `10.0.2.2` and `localhost` (previously *no* config, so Android 9+ would have blocked the debug `http://10.0.2.2:8000` base URL entirely). Build ✅.
- `.gitignore`: added `*.log`, `*.pid`, `celerybeat-schedule*`, `.env`, `__pycache__/`, venvs, tool caches.
- `docker-compose.yml`: dev defaults for secrets are clearly named `dev-only-…` and are rejected by the new production validator.
- **Not done:** rotating the secrets in `backend/.env` (dev values), removing the default `admin/admin123` prompts in `create_admin.py`, wiring rate limiting, cert-pin placeholders, Maps key, FCM `google-services`.

## 10. Data-model coherence, migrations, tests, Android login — 2026-09-27
Scope: `User.status`, migration reconciliation, stale tests, device identity / Android login. No dependency upgrades.

**Result:** backend `35 passed / 127 errors` → earlier `47 / 13 / 102` → **178 passed, 0 failed, 0 skipped** (tests grew 162 → 178: +13 login/device/status, +3 migration). `alembic check`: large drift → **clean**. `bazel build //app:amanah` ✅, `bazel test //...` 4 → **6/6** ✅ (+DeviceIdentity, +LoginRequest wire format; opt-in live contract test passes). Docker stack healthy; login + `/users/me` 200.

### Decisions
- **`users.status`** — investigation: referenced by `UserRepository.create/suspend/activate`, admin search filters, `UserStatus` enum (5 states) and ~45 test fixtures, but absent from the model and migrations, while all *enforcement* (login, `get_current_user`, presence, nearby) uses `is_active/is_verified/is_suspended`. → persisted native enum `user_status_enum` (lifecycle state of record), flags stay as enforcement, kept consistent by a `@validates` hook + repo transitions; existing rows back-filled in 008 (`deactivated` > `suspended` > `pending_verification` > `active`). `PENDING_ACTIVATION` is set only by workflow code (cannot be derived from flags).
- **Migrations** — `008_reconcile_schema_with_models` (models were authoritative; migrations 001–007 had drifted since the project was bootstrapped with `create_all` + `stamp`): `admin_approvals` table, `users.status`, id widening 32→36 (45 columns), 11 VARCHAR→native-enum columns (with `USING` casts), JSONB→JSON, `ip_address`→INET, nullability, FK `ON DELETE` rules, `ix_*`→`idx_*` + the composite/status/gist indexes, `altitude_m`, `max_attempts`, dropped unused `trusted_contacts.is_verified`. `009_device_identity_and_totp`: devices → contract (renames + `device_uuid`/`platform`/`is_primary`, unique `(user_id, device_uuid)`), `users.totp_secret_encrypted` (existing `mfa_secret` encrypted in place), `users.created_by_id`. Both are **idempotent** (inspect-then-act) so a legacy models-bootstrapped DB converges too. Historical migrations untouched. `env.py` ignores PostGIS-owned tables; `alembic.ini` black hook (not installed) disabled, file template = revision id. `tests/test_migrations.py` proves: empty → head clean; 007 DB **with data** → head (status back-fill, enum casts, device/TOTP data preserved) clean; legacy DB → head clean.
- **Device identity / login** — backend: `AuthService.login` now registers/refreshes the device (idempotent per `(user, device_uuid)`), binds JWT `device_id` and `refresh_tokens.device_id` to `devices.id` (previously `device_id=None` — "device registration not implemented"), refresh rotation keeps the binding, first device is primary, a *new* device beyond 10 retires the stalest non-primary one instead of blocking login. Android: `DeviceIdentity` = random v4 UUID generated once per installation and persisted in app-private SharedPreferences that survives sign-out (not per-login, not ANDROID_ID); `LoginRequest` sends `device_uuid`, `platform=android`, `app_version`; device registration DTO renamed `fcm_token`→`push_token` (server ignored the old name, so push tokens were never stored) and the FCM path now uses `DeviceIdentity` instead of `ANDROID_ID`.

### Application bugs found and fixed (tests exposed them; the tests were *not* loosened)
`request.<enum>.value` on `use_enum_values=True` schemas → `AttributeError` on every OTP / password-reset / device-register request (new `enum_value()`); OTP wrong-attempt count off by one and never rate-limited on the exhausting attempt; `AuthService.verify_otp` reported "expired" instead of rate-limit once attempts were spent; OTP/contact `destination_hash` used salted Argon2 so the duplicate-request lookup could never match (now keyed HMAC `hash_contact`, also `users.phone_hash/email_hash`); password-reset OTP looked up by *reset-request id* == *OTP id* (never true) → newest valid OTP for (user, purpose, channel); `InvalidCredentialsError` could not take a message (inactive login → TypeError; now generic, no account-state leak); Core-style `Model.__table__.update()/delete()` left stale ORM instances (device primary/deactivate-all, tokens, notifications, roles…) → session-synchronised ORM statements; all `Mapped[datetime]` columns were naive while code writes aware UTC (asyncpg error) → `type_annotation_map` (TIMESTAMPTZ); `IncidentRepository.update_status` logged the *new* status as `old_status`; nearby-responder query matched users with *any* role (or none at all when none existed) instead of `responder` (now EXISTS on role name); admin incident `severity` filter cast a PG enum to `str`; WebSocket auth read `payload.get("sub")` on a pydantic `TokenPayload` (every handler-based connection failed); `NotificationService.send_push_notification` was a stub that marked everything SENT with a fake id (now sends through the FCM provider off the event loop; added `dispatch_to_user`, `mark_delivered`, `retry_failed_notifications`); `UserService/DeviceService` device limit blocked re-registering a *known* device; `MFAVerifyRequest` attribute mismatch in the endpoint; `create_admin.py` created role `admin` (unknown to RBAC → every admin endpoint 403) → `super_admin` (upsert) and now writes `status`.

### Tests changed because the expectation was demonstrably obsolete (each documented in code or here)
| Test / fixture | Why obsolete → change |
|---|---|
| `create_sos` returning `(incident, pin)` (5 tests + fixtures) | No PIN concept exists in the app (see KNOWN_ISSUES #10); repo returns `Incident` → unpack one value, dropped the two `pin` asserts |
| `repo.cancel()/resolve()`, `IncidentStatus.CANCELLED`, `mark_en_route/arrived` | Methods never existed; behaviour is `update_status(...)`/`update_assignment_status(...)`; enum is `CANCELED` → same assertions on the real API |
| `test_resolve_incident` skipped ARRIVED | README §8 state machine only allows RESOLVED from ARRIVED → walk ACCEPTED→EN_ROUTE→ARRIVED first |
| `OTPPurpose.REGISTRATION` | Not an enum member (registration OTP = `PHONE_VERIFICATION`) |
| `User(phone_number=…)`, `Device(device_model=…, fcm_token=…)` fixtures | Fields never existed / renamed → `phone=`, `push_token=`, `device_uuid=` (+ required org/region/password) |
| `mark_read(notification.id)` | Real API is `mark_read(user_id, notification_ids)` (batch, used by the endpoint) |
| `@patch("…NotificationService.fcm_provider")` | Instance attribute, not class attribute → `patch.object(service.fcm_provider, "send")`; now also asserts the recipient token |
| weak-password test built the request *outside* `pytest.raises` | The schema itself must reject it → `pytest.raises(ValidationError)` around construction |
| trusted-contact mask asserted `"+880" not in masked` | `mask_phone` is documented to keep first 5 + last 5 chars → assert exact `+8801****56789` and that the full number is absent (stricter) |
| device "unauthorized access" used a non-existent user | Service checks the caller exists first → create a real second user; still expects `DeviceNotFoundError` |
| admin tests referenced `usr_admin`, `usr_approver`, `role_test`, `usr_incident_creator` that were never created | FK targets now created by fixtures |
| geospatial fixture lacked the `responder` role; loop used a lazy-load expression | Assign the role (required by design); simplify coordinates |
| `conftest.py` | Enum types derived from the models (no hand-maintained list) |

### Not done / not verifiable
- APK on emulator/device: **not possible on this host** (no `/dev/kvm`; AVD `amanah` fails to start). Substitute evidence: opt-in `//feature-core:LoginContractLiveTest` runs the real ApiFactory/Retrofit/Gson/DeviceIdentity against the live backend (login 200 → `/users/me` 200; DB shows one `android` device row, bound refresh token). R8 obfuscates class names, so the APK was inspected only via manifest (targetSdk 36, network-security config present).
- `GET /admin/users` returns 500 (pre-existing lazy-load bug); profile DTO / admin endpoint contract gaps — see KNOWN_ISSUES.

## Removed (files/config)
- `WORKSPACE` (moved to session scratchpad, not deleted from disk backup): Bazel 8 does not read it by default; verified `bazel build //app:amanah` succeeds without it and nothing references `@androidsdk_legacy`.
- `maven_install.json` empty placeholder → replaced with a real lock file.
- Dependencies listed above. **Not** removed (still PROBABLY_UNUSED, need owner sign-off): root `requirements.txt` (ML stack unrelated to the backend), `backend/backend.log`, `backend/backend.pid`, `backend/celerybeat-schedule`, `backend/app/websocket_v2.py`, `backend/app/api/v1/websocket.py`, NullAway/`//:nullaway_plugin` (Java-only tool wired as a Kotlin compiler plugin), `.bazelrc` legacy Android flags (deprecated but still accepted; `--fat_apk_cpu` builds arm64+x86_64).

## Final verification (2026-09-27)
| Check | Result |
| --- | --- |
| `bazel build //app:amanah` (Bazel 8.8.1, pinned lock file) | ✅ success, `amanah.apk` 5.8 MB |
| `bazel test //...` | ✅ 4/4 pass |
| Backend `pip check`, `import app.main` | ✅ |
| Backend pytest (real PG18/PostGIS) | ⚠️ 47 pass / 13 fail / 102 error — all pre-existing test↔model drift (see group 5) |
| Docker stack (5 services) | ✅ all healthy; login smoke test OK |
| ruff / mypy | not run |
| Android on emulator/device | not run |
