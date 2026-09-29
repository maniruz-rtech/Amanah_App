# PostgreSQL Integration Plan

The backend's relational layer is already production-grade. This document
catalogues the **small, focused** server-side work needed to support the
end-to-end persistence story.

---

## 1. What's already done (do not re-build)

- `postgis/postgis:16-3.4` container in `docker-compose.yml` with healthcheck.
- SQLAlchemy 2.0 async + asyncpg, with `pool_pre_ping=True`, pool 20 + 20.
- Alembic 1 revision covering 18 tables + `CREATE EXTENSION IF NOT EXISTS postgis`.
- `get_db()` request-scoped session with commit-on-success / rollback-on-exception.
- `BaseRepository` with the standard CRUD primitives.
- `IncidentRepository`, `UserRepository`, `AuditLogRepository`, etc. with real
  PostGIS writes (`ST_SetSRID(ST_MakePoint(lng, lat), 4326)`).
- Soft delete via `SoftDeleteMixin` on relevant tables.
- ULID-with-prefix IDs (`usr_…`, `inc_…`, `loc_…`, `evt_…`, `asgn_…`).
- Index coverage on every FK + commonly filtered column.

If you're skimming and looking for "what to fix on the backend": **only sections 3 and 4 below need actual code changes**.

---

## 2. Configuration surface

`backend/app/core/config.py` already exposes everything that needs to be
environmentalised:

| Env var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://amanah:amanah@localhost:5432/amanah` | Must use `+asyncpg` for the async engine. |
| `DATABASE_POOL_SIZE` | 20 | Increase per backend instance under load. |
| `DATABASE_MAX_OVERFLOW` | 20 | Burst capacity. |
| `DATABASE_POOL_TIMEOUT` | 30 | Seconds before raising `TimeoutError`. |
| `DATABASE_ECHO` | false | Set true for SQL logging (debug only). |
| `JWT_SECRET_KEY` | `CHANGE-ME-…` | **CI must reject the default in release.** |
| `ENCRYPTION_KEY` | `CHANGE-ME-32-…` | Same. |

Add `backend/.env.example` (currently missing) to document these.

---

## 3. New backend work required

### 3.1 Add `/api/v1/users/nearby` endpoint  (highest-priority addition)

The Android Home tab needs a list of active members in the user's H3 district
cell. The backend currently has *no* such endpoint.

**Plan:**

- New repository method: `UserRepository.get_active_in_h3_kring(h3_cell: str, k: int = 1) -> list[User]`.
  Use PostGIS `ST_DWithin` on the last-known location *or* — preferred — store
  the user's last H3 cell as a column (`users.last_h3_cell_district`,
  `users.last_h3_cell_block`) populated by presence pings. The H3 column is a
  cheap string index; no PostGIS query needed.
- New schema: `app/schemas/user.py:NearbyUserResponse(user_id, display_name, h3_cell, last_seen_at)`.
- New endpoint: `GET /api/v1/users/nearby?radius_k=1` in `app/api/v1/users.py`.
- Privacy: never return raw lat/lng. Only the obfuscated H3 cell is returned.
  The client applies `LocationPrivacyFilter.obfuscate(...)` for display only when
  no exact GPS is known.

### 3.2 Make WebSocket handlers persistent

Currently `websocket_v2._handle_emergency_alert` is a TODO. Two design options:

**Option A — single-source-of-truth REST (recommended).**
- Forbid `emergency.alert` envelopes from the client.
- Client triggers SOS via `POST /api/v1/incidents/sos` (which persists).
- Server then fans out the resulting `emergency.alert` envelope via the
  ConnectionManager so connected listeners get it instantly.
- WS becomes *delivery-only* for emergency events.
- Net benefit: one canonical persistence path; audit + state machine in one
  place.

**Option B — dual-path with WS handler calling service.**
- `_handle_emergency_alert(user_id, payload)` calls `IncidentService.create_sos`
  with the same JWT-derived user_id.
- Server then broadcasts to listeners as today.
- Net cost: two paths to keep in sync.

**Recommendation: option A.** The WS save is a microoptimisation that adds an
audit-bypass attack surface. The latency difference is < 100 ms which doesn't
matter for an emergency alert that takes seconds to type the long-press anyway.

### 3.3 Harden `/health`

Currently `/health` (in `app/api/v1/health.py`) returns 200 unconditionally.
Add a real probe:

```python
@router.get("/health")
async def health(db: DBSession) -> dict:
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "up" if db_ok else "down",
        "version": settings.app_version,
    }
```

Return 503 when `db_ok is False` so Kubernetes / docker-compose healthchecks
treat the backend as failing.

### 3.4 Refresh-token hardening

Inspect `RefreshTokenRepository.create` — confirm whether refresh tokens are
stored hashed (HMAC-SHA-256 with `JWT_SECRET_KEY`) or in plaintext. If
plaintext, a DB dump yields all current sessions. Fix:

- Add `token_hash` column to `refresh_tokens` (32 bytes, indexed).
- Replace `token` column with `token_hash`.
- On verify: hash the incoming token, look it up by hash, constant-time compare.
- Migration: existing rows are invalidated (forced re-login is acceptable).

### 3.5 Row-level multi-tenancy enforcement

Every repository query that selects from `users`, `incidents`,
`emergency_locations`, etc. *must* filter by `organization_id` derived from
the authenticated user's JWT. The current code does this in services
correctly (inspected `IncidentService.create_sos`); but there's no DB-level
enforcement.

Long-term: PostgreSQL Row-Level Security policies keyed by
`current_setting('app.organization_id')`, set by `get_db()` before the request
runs.

Short-term: add a `pytest` test that calls every repository method without an
org filter and asserts the result is filtered (or raises). Catches future
regressions.

---

## 4. Infrastructure work

### 4.1 `backend/.env.example`

Create at `backend/.env.example`:

```
ENVIRONMENT=local
DEBUG=true

# Database (must use +asyncpg)
DATABASE_URL=postgresql+asyncpg://amanah:amanah@localhost:5432/amanah
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=20

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT — generate a fresh value for every environment
JWT_SECRET_KEY=please-replace-with-32-bytes-of-random
ENCRYPTION_KEY=please-replace-with-exactly-32-bytes

# CORS — Android emulator hits localhost via 10.0.2.2
CORS_ORIGINS=http://localhost:3000,http://10.0.2.2

# Push
FCM_ENABLED=false
```

### 4.2 Migration in container startup

`docker-compose.yml` currently runs `uvicorn` immediately; first request
errors with "table does not exist" if migrations were never applied. Add an
init container or modify the API command:

```yaml
api:
  command: >
    bash -c "alembic upgrade head &&
             uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
```

(Or use a separate `migrate` service with `depends_on` ordering.)

### 4.3 Seed script

`backend/create_admin.py` exists; ensure it's idempotent and seeds:
- 1 organisation (`org_demo`),
- 1 region (`reg_demo`),
- 1 super-admin (`admin@demo.amanah` / `Demo1234!`),
- 1 regular user (`user@demo.amanah` / `Demo1234!`).

Add a `Makefile` target `make seed-demo` so demo setup is one command.

### 4.4 CI database setup

GitHub Actions (or equivalent):

```yaml
jobs:
  backend-test:
    services:
      postgres:
        image: postgis/postgis:16-3.4
        env:
          POSTGRES_USER: amanah
          POSTGRES_PASSWORD: amanah
          POSTGRES_DB: amanah_test
        ports: ['5432:5432']
        options: --health-cmd pg_isready --health-interval 10s
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r backend/requirements.txt
      - env:
          DATABASE_URL: postgresql+asyncpg://amanah:amanah@localhost:5432/amanah_test
        run: |
          cd backend
          alembic upgrade head
          pytest tests/
```

---

## 5. Order of operations

```
1.  Add backend/.env.example                           (15 min)
2.  Patch /health endpoint with DB probe               (30 min)
3.  Patch docker-compose to run alembic upgrade head    (15 min)
4.  Add backend/Makefile seed-demo target              (30 min)
5.  Add UserRepository.get_active_in_h3_kring + endpoint (3 h)
6.  Rewrite websocket_v2._handle_emergency_alert to delegate (or remove) (2 h)
7.  Refresh-token hashing migration                    (4 h)
8.  CI workflow                                        (2 h)
9.  Repository-level tenant-filter regression tests    (4 h)
```

**Total: 16 engineer-hours = 2 days for one engineer.**

After this, the backend is genuinely ready to be the persistence target for
the client rewiring work in [DATABASE_IMPLEMENTATION_STEPS.md](DATABASE_IMPLEMENTATION_STEPS.md).

---

## 6. Non-goals

Out of scope for this plan; tracked separately:
- Postgres read replica.
- PgBouncer transaction pooling.
- TimescaleDB for `emergency_locations` (timeseries).
- pg_partman partitioning of `incident_events` / `audit_logs`.
- Move audit logs to an append-only table with statement-level triggers.
- Postgres Row-Level Security policy graph (Schema work; needs design doc).
