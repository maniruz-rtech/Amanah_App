# End-to-End Validation

## The smoke test

`scripts/smoke_e2e.sh` is the single, scripted proof that the platform's
persistence chain works.

### What it does

1. Hits `/api/v1/health` — must return `{"status":"healthy", ...}`.
2. POSTs to `/api/v1/auth/login` with the seeded admin — receives a JWT.
3. GETs `/api/v1/users/me` with the JWT — confirms the token is honored.
4. Snapshots row counts in `incidents`, `emergency_locations`,
   `incident_events`, `audit_logs`.
5. POSTs to `/api/v1/incidents/sos` with `{lat:23.8103, lng:90.4125,
   severity:"high", incident_type:"sos"}` — must return 201 +
   `incident_id`.
6. Re-counts the four tables and asserts every delta is ≥ 1.
7. Pulls the PostGIS column via `ST_AsText(location)` and asserts the
   point matches the trigger coordinates.
8. Confirms the incident is queryable with `status = broadcasting`.

### Latest run output

```
$ ./scripts/smoke_e2e.sh

✔ API healthy: {"status":"healthy","version":"1.0.0","environment":"dev", ...}
✔ logged in as usr_01KS5ZCBVVJYQMJ5N3AVMCVQQ6
✔ /users/me returns matching user
✔ incidents=1 emergency_locations=1 incident_events=1 audit_logs=5
✔ incident created: inc_01KS5ZKGSAR3Z1XB0C44EASWPW
✔ deltas: incidents +1, locations +1, events +1, audit +1
✔ ST_AsText(location) = POINT(90.4125 23.8103)
✔ incident status: broadcasting

✔ PASS — end-to-end persistence chain verified.
    incident_id : inc_01KS5ZKGSAR3Z1XB0C44EASWPW
    user_id     : usr_01KS5ZCBVVJYQMJ5N3AVMCVQQ6
    rows added  : 1 incident + N events + 1 audit_log + 1 emergency_location
    final state : broadcasting (post-trigger)
```

### Exit codes

The script returns the failing step number on first failure. Useful for CI
chaining:

| Code | Meaning |
|---|---|
| 0   | All steps passed |
| 1   | API unreachable |
| 2   | Login failed |
| 3   | /users/me failed |
| 5   | SOS POST failed |
| 6   | DB delta wrong |
| 7   | PostGIS point mismatch |
| 99  | Missing dependency (jq, curl) |
| 90  | DB container not found |

---

## Manual Android validation

After running the smoke against the backend, install the Android client:

```bash
bazel build //app:amanah
adb install -r bazel-bin/app/amanah.apk
adb shell am start -n com.amanah.app/.MainActivity
adb logcat OkHttp:V '*:S' &
```

Then manually:

1. **Login screen** — enter `admin` / `Demo1234!`.
   - **Expected**: logcat shows `POST /api/v1/auth/login → 200`.
   - Followed by `GET /api/v1/users/me → 200`.
   - UI routes to Admin Dashboard.

2. **Admin Dashboard / Users tab** — should show **at least the admin
   account itself** (no Aisha/Omar). If it shows fake names, the build
   wasn't picked up.

3. **Sign out**, sign in as a regular user (after seeding one). Land on
   User Dashboard.

4. **Long-press the red EMERGENCY button**.
   - **Expected logcat**: `POST /api/v1/incidents/sos → 201`.
   - **Expected DB** (`psql`):
     ```sql
     SELECT id, status, created_at FROM incidents ORDER BY created_at DESC LIMIT 1;
     SELECT action FROM audit_logs ORDER BY created_at DESC LIMIT 1;
     ```
     A fresh row in each.

5. **Kill the app and relaunch**.
   - **Expected**: app routes **directly to the User Dashboard**, skipping
     login (session rehydration verified).

6. **Sign out** from the Profile tab.
   - **Expected logcat**: gateway disconnects, token store cleared.
   - Relaunch → routes to Login.

---

## Cross-process realtime test

On two devices (or two emulators):

1. Sign in as admin on Device A.
2. Sign in as user on Device B.
3. Trigger SOS on Device B.
4. **Device A** should:
   - Receive a fresh row in the Alerts tab within ≤ 2 s (via WS).
   - Show the alert with status `ACTIVE` and red border.
5. Tap the alert on Device A → AdminAlertDetail.
6. Press "Force Resolve" → reason dialog → confirm.
7. **Device B** should:
   - Receive the resolve event over WS.
   - The active-emergency overlay closes.

(This is the demo flow; see [MVP_GAP_CLOSURE_PLAN.md](MVP_GAP_CLOSURE_PLAN.md).)

---

## What the smoke does NOT cover

These are documented gaps to address in the next iteration:

- The Android side of the chain (the smoke is backend-only).
- Realtime fanout (no WS subscriber asserted in the smoke).
- Resolve / cancel state-machine path (requires multi-step transitions
  or admin verification_pin).
- Reconnect recovery (requires a flaky-network harness).
- Token refresh on 401 (requires forced token revocation).
- TLS pinning failure (requires mitmproxy).

Each is unit-testable in isolation today against the components we've
shipped; a richer integration harness is the next step.

---

## CI integration

To wire the smoke into a CI pipeline:

```yaml
# .github/workflows/backend-smoke.yml (sketch)
name: backend-smoke

on: [push, pull_request]

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start stack
        run: |
          cd backend
          docker compose up -d db redis api
          # wait for healthy
          timeout 90 bash -c 'until docker compose ps api | grep -q "healthy"; do sleep 2; done'
      - name: Initialise schema
        run: |
          docker compose exec -e PYTHONPATH=/app api python scripts/init_schema_from_models.py
          docker compose exec -e PYTHONPATH= api alembic stamp head
      - name: Seed admin
        run: |
          printf 'admin\nDemo1234!\nAdmin\n+8801700000000\nadmin@demo.amanah\n' \
            | docker compose exec -T -e PYTHONPATH=/app api python create_admin.py
      - name: Run smoke
        run: bash scripts/smoke_e2e.sh
```

The smoke exit-codes integrate naturally with CI failure semantics.
