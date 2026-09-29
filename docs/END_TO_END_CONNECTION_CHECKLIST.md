# End-to-End Connection Checklist

A no-trust verification harness. Walk through this once before declaring any
release candidate "connected." Each section is a script you can run.

---

## 1. Backend DB validation

```bash
cd /home/mzaman/Amanah_App/backend

# 1.1 Bring up the database
docker-compose up -d db redis
docker-compose ps db
# Expect: STATUS = "Up (healthy)"

# 1.2 Connect manually
docker-compose exec db psql -U amanah -d amanah -c "SELECT version();"
# Expect: a PostgreSQL 16 version string

# 1.3 Confirm PostGIS is enabled
docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname='postgis';"
# Expect: postgis | 3.4.x

# 1.4 Run migrations
docker-compose run --rm api alembic upgrade head
# Expect: "Running upgrade -> 001_initial" and final state

# 1.5 Verify schema
docker-compose exec db psql -U amanah -d amanah -c "\dt"
# Expect: 18 tables incl. organizations, regions, users, incidents,
#         emergency_locations, incident_assignments, audit_logs

# 1.6 Verify spatial index on emergency_locations
docker-compose exec db psql -U amanah -d amanah \
  -c "\d emergency_locations" | grep -i location
# Expect: location | geography(POINT, 4326)

# 1.7 Seed demo data
docker-compose run --rm api python create_admin.py
# Expect: admin user created
```

---

## 2. Backend API validation

```bash
# 2.1 Start the API
docker-compose up -d api
sleep 5  # give it a moment

# 2.2 Health probe
curl -s http://localhost:8000/api/v1/health | jq .
# Expect (after patching health.py): {"status":"ok","db":"up","version":"..."}

# 2.3 Login as the seeded admin
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin@demo.amanah","password":"Demo1234!"}' \
  | jq -r .access_token)
echo "Token length: ${#TOKEN}"
# Expect: a long string

# 2.4 Verify /users/me
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/users/me | jq .
# Expect: { "id":"usr_...", "username":"admin@demo.amanah", ... }

# 2.5 Trigger an SOS via REST — VERIFY DB ROW
curl -s -X POST http://localhost:8000/api/v1/incidents/sos \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"lat":23.8103,"lng":90.4125,"severity":"HIGH"}' \
  | jq .
# Expect: { "incident_id":"inc_...", "status":"broadcasting", ... }

docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT id, status, created_by_id FROM incidents ORDER BY created_at DESC LIMIT 1;"
# Expect: a row matching the response above

# 2.6 Confirm audit_logs row was written
docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT action, resource_type FROM audit_logs ORDER BY created_at DESC LIMIT 1;"
# Expect: action='sos_created' | resource_type='incident'

# 2.7 Confirm emergency_locations row with PostGIS
docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT id, ST_AsText(location) FROM emergency_locations ORDER BY captured_at DESC LIMIT 1;"
# Expect: POINT(90.4125 23.8103)
```

---

## 3. WebSocket validation

```bash
# 3.1 Install wscat
npm install -g wscat || pip install websocat

# 3.2 Connect with header auth (header-auth endpoint websocket_v2)
wscat -c ws://localhost:8000/ws \
      -H "Authorization: Bearer $TOKEN"
# Expect: connection accepted; first frame is the auth.accepted envelope

# 3.3 Verify ping/pong
> {"v":1,"type":"ping","event_id":"e1","ts":1715000000000,"payload":{}}
# Expect: < {"v":1,"type":"pong",...}

# 3.4 Verify ACK
> {"v":1,"type":"presence","event_id":"e2","ts":1715000000000,"payload":{"h3_cell":"872bedfd5ffffff","online":true}}
# Expect: < {"v":1,"type":"ack","payload":{"event_id":"e2"}}

# 3.5 Verify emergency.alert is REJECTED (after fix)
> {"v":1,"type":"emergency.alert","event_id":"e3","ts":1715000000000,"payload":{"lat":23.81,"lng":90.41}}
# Expect (after fix): error envelope or no DB write
docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT COUNT(*) FROM incidents WHERE created_at > NOW() - INTERVAL '10 seconds';"
# Expect: 0 (WS path does NOT persist)

# 3.6 Verify presence DOES persist (after fix)
docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT last_h3_cell_district FROM users WHERE username='admin@demo.amanah';"
# Expect: 872bedfd5ffffff
```

---

## 4. Android integration validation

```bash
# 4.1 Build the app
cd /home/mzaman/Amanah_App
bazel build //app:amanah

# 4.2 Install on emulator and launch
adb install -r bazel-bin/app/amanah.apk
adb shell am start -n com.amanah.app/.MainActivity

# 4.3 Monitor network traffic
adb logcat OkHttp:V '*:S' &

# 4.4 Sign in as user@demo.amanah / Demo1234! via the UI
# Expect in logcat: POST /api/v1/auth/login 200
#                   followed by GET /api/v1/users/me 200
```

**Manual verification points:**

- After login, the User Dashboard's nearby grid should show real users (the
  ones seeded by `make seed-demo`), NOT "Aisha" / "Omar". If it shows the
  stub names, `UserFeature` is not wired to `UserRepository` yet.
- Long-press the red EMERGENCY button. Verify in `psql`:
  ```
  SELECT COUNT(*) FROM incidents WHERE created_at > NOW() - INTERVAL '30 seconds';
  ```
  Expect 1 (was 0 before the fix).
- Sign in on a second device/emulator as `admin@demo.amanah`. Within 2 s
  of the SOS trigger, the admin's Alerts tab should show a new row with
  status `ACTIVE`. If it doesn't, the WS fanout is broken.
- In the admin tab, tap an alert → AdminAlertDetail screen. The displayed
  victim + responder list should match what's in `psql`:
  ```
  SELECT * FROM incident_assignments WHERE incident_id = '<id>';
  ```
- Tap "Force Resolve". Expect `incidents.status = 'resolved'` in `psql`
  and the alert disappears from the admin's active list.

---

## 5. Persistence verification (post-fix)

```bash
# 5.1 SOS round-trip persistence
adb shell input touchscreen swipe 540 1500 540 1500 1500  # long-press emergency
sleep 1
docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT id, status, created_by_id FROM incidents ORDER BY created_at DESC LIMIT 1;"
# Expect: a fresh row whose created_by_id matches the logged-in user

# 5.2 Audit log integrity
docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT action, actor_user_id, created_at FROM audit_logs ORDER BY created_at DESC LIMIT 5;"
# Expect: sos_created and a chain of related events

# 5.3 Geographic data integrity
docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT id, lat, lng, ST_X(location::geometry), ST_Y(location::geometry) FROM emergency_locations ORDER BY captured_at DESC LIMIT 1;"
# Expect: lat/lng match ST_Y/ST_X

# 5.4 Soft delete test
TC_ID=$(curl -s -X POST http://localhost:8000/api/v1/users/trusted-contacts \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"display_name":"Test","phone":"+15555550100"}' | jq -r .id)
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/users/trusted-contacts/$TC_ID
docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT id, deleted_at FROM trusted_contacts WHERE id='$TC_ID';"
# Expect: deleted_at IS NOT NULL (soft delete)
```

---

## 6. Offline / recovery validation

```bash
# 6.1 Outbound queue durability test
# Connect to staging WiFi, kill API container:
docker-compose stop api
# Long-press emergency on the device.
# Expect: UI shows "queued — will send when online" (after durable queue fix)
# Restart API:
docker-compose start api
sleep 5
# Expect within 30 s: an incidents row in psql

# 6.2 Process death recovery
# Reproduce the SOS-while-offline state, then kill the app process:
adb shell am force-stop com.amanah.app
# Restart:
adb shell am start -n com.amanah.app/.MainActivity
# Expect (after DataStore-Proto durable queue lands): the queued envelope
# flushes; an incident row appears in psql.

# 6.3 Token persistence
adb shell am force-stop com.amanah.app
adb shell am start -n com.amanah.app/.MainActivity
# Expect (after session rehydration lands): user is taken DIRECTLY to the
# dashboard, not the login screen.

# 6.4 Logout cleanup
# Trigger logout from Profile tab.
adb shell run-as com.amanah.app ls /data/data/com.amanah.app/files/datastore/
# Expect: amanah_tokens.preferences_pb is present but empty
adb shell run-as com.amanah.app ls /data/data/com.amanah.app/shared_prefs/
# Expect: amanah_keyset_prefs.xml absent (rotated on logout)
```

---

## 7. Migration validation

```bash
# 7.1 Migrate forward from scratch
docker-compose down -v       # drop all data
docker-compose up -d db redis
docker-compose run --rm api alembic upgrade head
# Expect: no errors; all 18 tables created

# 7.2 Verify revision marker
docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT version_num FROM alembic_version;"
# Expect: 001_initial (or the latest revision after refresh-token-hash etc.)

# 7.3 Migrate down (smoke test only — destructive)
docker-compose run --rm api alembic downgrade base
docker-compose exec db psql -U amanah -d amanah -c "\dt"
# Expect: only alembic_version table remains

docker-compose run --rm api alembic upgrade head
# Expect: clean re-creation

# 7.4 Autogenerate detection
docker-compose run --rm api alembic revision --autogenerate -m "no_changes"
ls backend/alembic/versions/*_no_changes.py
# Inspect — if the generated file has non-empty upgrade(), there's
# schema drift between models and migrations.
```

---

## 8. CI gate

The release pipeline should fail if any of the following is missing on
`main`:

- [ ] `backend/.env.example` exists.
- [ ] Default `JWT_SECRET_KEY` value not present in any committed `.env` file.
- [ ] Default `ENCRYPTION_KEY` value not present in any committed `.env` file.
- [ ] `alembic upgrade head` succeeds on a fresh Postgres in CI.
- [ ] `pytest backend/tests/` passes.
- [ ] `bazel build //app:amanah --compilation_mode=opt` succeeds.
- [ ] R8 produced no warnings about reflective-keep misses.
- [ ] No `// TODO: replace with .*Repository` markers in any feature module's
      Actor/Interactor (use `grep -rln "TODO.*Repository" feature-*/src` to enforce).
- [ ] `PinningConfig.PRIMARY_PIN` does not contain `REPLACE_WITH_`.

---

## 9. Pre-release smoke (60-second version)

If you can do **only one** check before tagging a release:

```bash
# 9.1 Spin everything from scratch
docker-compose down -v && docker-compose up -d && sleep 30
docker-compose run --rm api alembic upgrade head
docker-compose run --rm api python create_admin.py

# 9.2 Build the APK
bazel build //app:amanah

# 9.3 Install and trigger SOS via the UI
adb install -r bazel-bin/app/amanah.apk
adb shell am start -n com.amanah.app/.MainActivity
# log in, long-press emergency, wait 5 s

# 9.4 Confirm persistence
docker-compose exec db psql -U amanah -d amanah \
  -c "SELECT id, status, created_at FROM incidents ORDER BY created_at DESC LIMIT 1;"
```

If step 9.4 returns a row whose `created_at` is within the last minute, the
end-to-end persistence path is connected. **If it returns no row, the system
is NOT connected — do not ship.**

---

## 10. Sign-off

A release is considered "connected" when:

- All checks in §1 pass (DB layer healthy).
- All checks in §2 pass (REST API persistence).
- All checks in §3 pass (WS transport + the right-things-don't-persist
  semantics post-fix).
- §4 manual flow shows real data in every dashboard tab.
- §5 confirms every flow leaves an audit trail.
- §6 confirms offline survivability.
- §7 confirms migrations work both directions.
- §8 CI gate is green.

Sign-off recorded in the release ticket with the timestamp of the §9 smoke
check.
