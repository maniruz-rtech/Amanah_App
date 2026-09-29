# Release Validation Checklist

Run through this list before tagging any release-candidate build. The
list is split into **backend**, **client**, and **end-to-end** sections.
Each item maps to a verification command — copy/paste rather than
trusting memory.

## Backend

- [ ] `docker compose up -d` brings up db + redis + api + celery_worker
      + celery_beat in < 60 s.

  ```bash
  cd backend && docker compose up -d && sleep 60
  docker compose ps
  ```

- [ ] `/api/v1/health` reports `status: healthy`, both subsystems up.

  ```bash
  curl -sS http://localhost:8000/api/v1/health | jq .
  ```

- [ ] `/api/v1/ready` returns 200 when healthy, 503 when DB or Redis is
      down (test by stopping Redis).

- [ ] `alembic upgrade head` is a no-op (i.e. the migration table is at
      the latest revision).

  ```bash
  docker exec -e PYTHONPATH= -w /app amanah_api alembic current
  ```

- [ ] `scripts/smoke_e2e.sh` passes 8/8 from a clean DB.

  ```bash
  bash /home/mzaman/Amanah_App/scripts/smoke_e2e.sh
  # → "PASS — end-to-end persistence chain verified."
  ```

- [ ] All `pytest` tests pass.

  ```bash
  docker exec -w /app amanah_api pytest tests/ -x
  ```

- [ ] No `JWT_SECRET_KEY=dev-secret…` or `ENCRYPTION_KEY=dev-encryption…`
      in any deployed env. Greps must return zero hits:

  ```bash
  git grep -l "CHANGE-ME"          # source-side
  docker compose config             # rendered env
  ```

- [ ] `FCM_ENABLED=true` only in environments with a valid
      `FIREBASE_CREDENTIALS_PATH`.

## Client

- [ ] Bazel release build succeeds with R8.

  ```bash
  bazel build //app:amanah --compilation_mode=opt
  ```

- [ ] R8 produces no warnings about reflective-keep misses. Inspect the
      build log; any `Warning: Class … is referenced from …` is a
      potential runtime crash in release.

- [ ] `PinningConfig.PRIMARY_PIN` and `BACKUP_PIN` are not placeholders.
      Verify via `grep`:

  ```bash
  grep "REPLACE_WITH" feature-core/src/main/kotlin/com/amanah/feature/core/network/PinningConfig.kt
  # Expected: no output
  ```

- [ ] Release APK refuses to connect through a mitmproxy with a custom
      CA. Procedure in
      [CERTIFICATE_PINNING_PRODUCTION.md](CERTIFICATE_PINNING_PRODUCTION.md#pre-release-verification-mitmproxy).

- [ ] No `// TODO: replace with .*Repository` markers in feature
      modules:

  ```bash
  grep -rln "TODO.*Repository" feature-*/src 2>/dev/null
  # Expected: no output
  ```

- [ ] Firebase config (`google-services.json`) is present in app/
      and matches the `applicationId` (`com.amanah.app`).

- [ ] `MAPS_API_KEY` is set via Bazel `--define=MAPS_API_KEY=…` for
      release builds. Verify via `aapt dump badging amanah.apk |
      grep com.google.android.geo.API_KEY`.

- [ ] Unit tests pass (when bazel test wiring is added; currently the
      test sources are present in
      `feature-core/src/test/kotlin/` and
      `feature-emergency/src/test/kotlin/` but the BUILD targets for
      `kt_jvm_test` need to be added in the BUILD.bazel files — small
      follow-up).

## End-to-end

- [ ] On a fresh emulator:

  1. Install release APK.
  2. Onboarding flow renders correctly.
  3. Login with seeded admin credentials → land on Admin Dashboard.
  4. Logout → land on Login.
  5. Login with seeded user credentials → land on User Dashboard.
  6. Long-press the EMERGENCY button.
  7. Verify in `psql`:

     ```sql
     SELECT id, status, created_at FROM incidents
     ORDER BY created_at DESC LIMIT 1;
     ```

     A fresh row in `broadcasting` state, created within the last
     minute.

  8. Verify `audit_logs` has the matching `sos_created` row.
  9. Verify the foreground notification "Emergency in progress" is
     visible.
  10. Press "Cancel Emergency" (or admin force-resolve) → foreground
      notification dismisses.

- [ ] Kill the app via Settings → Apps → Force stop.

  1. Trigger a backend event that produces an FCM emergency push to
     the user.
  2. Verify the FCM notification surfaces on the device.
  3. Tap the notification → app launches; landed on the
     active-emergency overlay.

- [ ] Network flap test:

  1. Open the app, login, get to the dashboard.
  2. Disable wifi for 5 s.
  3. Enable wifi.
  4. Verify gateway state transitions: Online → Reconnecting → Online
     within ≤ 10 s. Watch logcat: `RealtimeGateway` tag.

- [ ] Cross-device coordination test (two emulators or two devices):

  1. Device A signed in as admin; Device B signed in as user.
  2. Device B long-press emergency.
  3. Within 2 s Device A's Admin Dashboard "Alerts" tab shows the
     fresh alert.
  4. Tap the alert on Device A → drill into AdminAlertDetail.
  5. Tap Force Resolve → confirm dialog → submit.
  6. Within 2 s Device B's emergency overlay closes.

## CI gate

Integrate this with CI by adding a GitHub Actions workflow that runs:

```yaml
- run: bash scripts/smoke_e2e.sh
- run: bazel test //feature-core/... //feature-emergency/...   # once kt_jvm_test targets are added
- run: bazel build //app:amanah --compilation_mode=opt
- run: grep -L "REPLACE_WITH" feature-core/src/main/kotlin/com/amanah/feature/core/network/PinningConfig.kt
```

The workflow fails on:
- Smoke regression
- Test regression
- R8 build failure
- Pin placeholder still present
