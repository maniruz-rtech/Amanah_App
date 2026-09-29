# Amanah

Verified-member community-safety platform — Android client + FastAPI backend.

## Repository layout

```
Amanah_App/
├── app/                   Android composition root (Bazel target //app:amanah)
├── backend/               FastAPI backend (vendored from amanah18)
├── feature-auth/          Login, password-reset, onboarding nodes
├── feature-core/          Shared infra: design system, networking, session,
│                          WebSocket, theme, debug drawer
├── feature-admin/         Admin dashboard + alert / user detail nodes
├── feature-user/          User dashboard + incident detail nodes
├── feature-emergency/     EmergencyFeature, EmergencyAlertEngine,
│                          ProximityMatcher
├── libraries/
│   ├── location/          H3 indexing + Box-Muller location obfuscation
│   └── nodes-framework/   In-house Node / Interactor / Router / View framework
├── scripts/               Bazel + dev helpers
└── *.md                   Audit, roadmap, and migration docs
```

## Quick start (customer demo)

### 1. Start the backend

```bash
cd backend
docker-compose up -d        # postgres+postgis, redis, fastapi, celery
docker-compose exec api alembic upgrade head
docker-compose exec api python create_admin.py   # seed an admin
```

Backend listens on `http://localhost:8000` (Android emulator reaches the host
on `http://10.0.2.2:8000` — already the default in `app/di/AppGraph.kt`).

### 2. Build & run the Android client

```bash
bazel build //app:amanah
bazel mobile-install //app:amanah   # or use Android Studio with bazel plugin
```

Sign in with the seeded admin user; long-press the red emergency button as a
demo user; the responder map will fill in with WebSocket-driven updates.

## Architecture

Single Activity → Compose UI → in-house `Node` framework with Badoo MVICore
2.x for state, Reaktive 2.x for streams, Scarlet for WebSocket. Backend is
FastAPI + PostgreSQL+PostGIS + Redis + Celery (full schema in
`backend/alembic/`). Privacy invariants live in `libraries/location/` — see
`LocationPrivacyFilter.kt` for the Box-Muller obfuscation model.

For the full audit and roadmap, read in order:

1. [PROJECT_AUDIT_AND_ROADMAP.md](PROJECT_AUDIT_AND_ROADMAP.md) — the deep audit
2. [UI_UX_MVP_PLAN.md](UI_UX_MVP_PLAN.md) — screen-by-screen plan
3. [FEATURE_COMPLETION_MATRIX.md](FEATURE_COMPLETION_MATRIX.md) — feature status
4. [TECHNICAL_DEBT_REPORT.md](TECHNICAL_DEBT_REPORT.md) — debt + security
5. [MIGRATION_PLAN_FROM_AMANAH18.md](MIGRATION_PLAN_FROM_AMANAH18.md) — port plan

## Demo accounts (after seeding)

| Role  | Email                | Password    |
|-------|----------------------|-------------|
| Admin | `admin@demo.amanah`  | `Demo1234!` |
| User  | `user@demo.amanah`   | `Demo1234!` |

(seed script values; change in `backend/create_admin.py`)

## Development

```bash
# Run the backend tests
cd backend && pytest

# Build the Android app
bazel build //app:amanah

# Run a specific feature's tests (none yet — see TECHNICAL_DEBT_REPORT E1)
bazel test //feature-emergency:tests
```

## Documentation

Each module has a thin `BUILD.bazel`. Cross-module deps:

```
app
├── feature-auth
│   └── feature-core
├── feature-admin
│   ├── feature-auth, feature-core
├── feature-user
│   ├── feature-auth, feature-core, feature-emergency
├── feature-emergency
│   └── feature-auth, feature-core
├── feature-core
│   └── libraries/nodes-framework
└── libraries/location, libraries/nodes-framework
```

## License

Proprietary — see internal docs.
