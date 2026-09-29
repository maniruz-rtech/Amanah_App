# Dependency Versions

Selected 2026-09-26/27. "Latest Stable" was queried from the upstream registries
that day: Maven Central / Google Maven / JitPack `maven-metadata.xml`, the Bazel
Central Registry (`bcr.bazel.build`), PyPI JSON API, GitHub Releases API
(`bazelbuild/bazel`), Docker Hub tags, and endoflife.date (support windows).
Pre-releases (alpha/beta/RC/dev/EAP) were excluded everywhere.

**Verification legend** — every "Selected" value below was built/run unless marked otherwise:
Android = `bazel build //app:amanah` + `bazel test //...` (pinned `maven_install.json`);
Backend = `pip check` + import + pytest + a live `docker compose` stack (login smoke test).

## 1. Build toolchain

| Component | Current | Selected | Latest Stable | Reason |
| --- | --- | --- | --- | --- |
| Bazel | 7.4.1 | **8.8.1** | 9.2.0 (8.8.1 is the newest 8.x LTS, EOL 2027-12) | Stay on the 8.x LTS line: 9.x removes WORKSPACE/legacy Android bits and rules_kotlin/rules_android Android support on 9 was not verified. 8.8.1 builds and tests green. Revisit 9.x after rules_android/rules_kotlin document 9.x Android support. |
| rules_android | 0.6.0 | **0.7.3** | 0.7.3 | Fixed the R8 failures (`Missing class android.view.RenderNode`, `*.R$id`) caused by 0.6.0 not merging AAR resources; Starlark `android_binary` (dropped the `multidex` attribute). |
| rules_kotlin | 2.1.0 | **2.4.20** | 2.4.20 | Matches Kotlin 2.4.20; registers its own default toolchain (old `kotlin_toolchain.register` extension removed). |
| rules_jvm_external | 6.3 | **7.1** | 7.1 | Current; supports lock file with Bazel 8. |
| bazel_skylib | 1.7.1 | **1.9.2** | 1.9.2 | Current. |
| platforms | 0.0.10 | **1.1.0** | 1.1.0 | Current. |
| Kotlin compiler | 2.1.0 | **2.4.20** | 2.4.20 | Latest stable; Compose compiler plugin must equal it (`kotlin-compose-compiler-plugin:2.4.20`). |
| Kotlin JVM target | 1.8 (implicit default) | **17** (custom `//:kotlin_toolchain`) | — | AndroidX/Compose ship JVM-11+ inline bytecode; 1.8 target fails to compile. 17 = Android-safe LTS target. |
| JDK (build tools) | 17 / remotejdk11 | **21** (Bazel `remotejdk_21`); Java language level 17 | 25 (LTS) | 21 LTS is what current R8/Error Prone tooling expects; no host JDK install required. 25 not needed. |
| Android compileSdk / targetSdk | 35 | **36** (Android 16) | 37.x preview-line platforms exist; 36 is the current stable API level | Play requires a recent target level; SDK platform-36 + build-tools 36.0.0 installed into `~/Android/Sdk`. |
| minSdk | 26 | 26 (unchanged) | — | Native multidex, no desugaring cost; no reason to change. |
| Android build-tools | 35.0.0 | **36.0.0** | 37.0.0 | 36.0.0 is the tools release paired with API 36; 37.0.0 not needed. |
| Android R8 | 8.5.35 (bundled) | bundled with rules_android 0.7.3 | — | Comes with the rules. |
| `maven_install.json` | empty placeholder | **real lock file** (`lock_file = "//:maven_install.json"`) | — | Reproducible, hash-pinned dependency resolution. Regenerate: `: > maven_install.json; REPIN=1 bazel run @maven//:pin`. |

## 2. Android / Kotlin dependencies

| Component | Current | Selected | Latest Stable | Reason |
| --- | --- | --- | --- | --- |
| kotlin-stdlib / kotlin-test | 2.1.0 | 2.4.20 | 2.4.20 | Follows compiler. |
| kotlinx-coroutines (core/android/test) | 1.9.0 (test: n/a) | 1.11.0 | 1.11.0 | Current; `-test` added for the unit tests. |
| Compose UI / foundation / animation / runtime / tooling | 1.7.5 | 1.12.1 | 1.12.1 | Current stable release train (BOM 2026.09.00). |
| Compose Material3 | 1.3.1 | 1.4.0 | 1.4.0 | Current stable. |
| Compose material-icons-extended / -core | 1.7.5 | 1.7.8 | 1.7.8 | Final release of the icons artifacts (no newer line). |
| Compose material (M2) + ripple | 1.7.5 | 1.12.1 | 1.12.1 | Only kept as a conflict pin for transitive strict versions (material3 pulls ripple). |
| activity-compose / activity / activity-ktx | 1.9.3 | 1.13.0 | 1.13.0 | Current. `activity`/`activity-ktx` pinned explicitly to resolve Gradle-metadata `[strict]` conflicts. |
| core-ktx / core | 1.15.0 | 1.19.1 | 1.19.1 | Current. |
| lifecycle (runtime-compose, runtime, process, common, viewmodel, livedata) | 2.8.7 | 2.11.0 | 2.11.0 | Current. |
| collection / collection-jvm | 1.4.4 | 1.6.0 | 1.6.0 | Current; pinned for strict-version conflicts. |
| savedstate / fragment | (transitive) | 1.5.0 / 1.9.1 | 1.5.0 / 1.9.1 | Conflict pins only. |
| emoji2 / startup-runtime | 1.3.0 / 1.2.0 | 1.7.0 / 1.2.0 | 1.7.0 / 1.2.0 | Current (manifest uses `InitializationProvider`). |
| datastore (core/preferences/…) | 1.1.1 | 1.2.1 (`datastore-preferences-android`) | 1.2.1 | Current. Root KMP artifact `datastore-preferences` has no jar → lock-file fetch 404; depend on the `-android` variant. |
| Tink (`tink-android`) | 1.13.0 | 1.23.0 | 1.23.0 | Security library — stay current. Compiled without code changes. |
| OkHttp (+ logging-interceptor) | 4.12.0 | 5.5.0 | 5.5.0 | Current stable major; compiled without code changes. |
| Retrofit (+ converter-gson) | 2.11.0 | 3.0.0 | 3.0.0 | Current; source-compatible for this project. |
| Gson | 2.11.0 | 2.14.0 | 2.14.0 | Current. |
| Firebase Messaging / Common | 24.0.0 / 21.0.0 | 25.1.3 / 23.0.0 | 25.1.3 / 23.0.0 | Current. (No `google-services` wiring yet — see PROJECT_STATE.) |
| Play Services Maps / Location | 19.0.0 / 21.3.0 | 20.0.0 / 21.4.0 | 20.0.0 / 21.4.0 | Current. |
| maps-compose | 6.2.1 | 8.6.0 | 8.6.0 | Current; compiled without code changes. |
| Uber H3 | 4.1.1 | 4.5.0 | 4.5.0 | Current. |
| Badoo MVICore | 1.4.0 | 1.4.0 | 1.4.0 (unmaintained upstream) | Structural dependency of the Nodes/MVI architecture. No newer release exists. Kept. |
| Badoo Reaktive | 2.3.0 | 2.4.0 | 2.4.0 | Current. |
| RxJava 2 | 2.2.21 | 2.2.21 | 2.2.21 (final of 2.x) | Required by MVICore 1.4's API. RxJava 3 not adoptable without replacing MVICore. |
| NullAway | 0.10.25 | 0.14.2 | 0.14.2 | Referenced by `//:nullaway_plugin` only (see PROJECT_STATE: currently a no-op for Kotlin). |
| android-weak-handler | 1.1 | 1.1 | 1.1 | Latest. |
| JUnit / MockK (`mockk-jvm`) | 4.13.2 / 1.13.12 | 4.13.2 / 1.14.11 | 4.13.2 / 1.14.11 | Current. `mockk` root is KMP with no jar → use `mockk-jvm`. |

## 3. Backend runtime & dependencies (Python 3.12)

| Component | Current | Selected | Latest Stable | Reason |
| --- | --- | --- | --- | --- |
| Python | 3.12 (image `python:3.12-slim`) | **3.12** (unchanged) | 3.14.7 (3.13.15 also current) | 3.12 is supported to 2028-10, every dependency ships wheels for it, it is what the code/CI were written and tested on. 3.13/3.14 give no measurable win for an I/O-bound async API and add wheel-availability risk (asyncpg, grpc, firebase). Revisit at the next dependency refresh. |
| FastAPI | 0.109.2 | 0.141.1 | 0.141.1 | Current; pulls Starlette 1.7.0 (fixes multiple past Starlette CVEs). App imports/starts cleanly, tests unchanged. |
| Uvicorn | 0.27.1 | 0.54.0 (`[standard]`) | 0.54.0 | Current. |
| Pydantic / pydantic-settings | 2.6.1 / 2.1.0 | 2.13.5 / 2.15.0 | 2.13.5 / 2.15.0 | Current. `class Config` deprecation warnings remain (still valid until Pydantic v3). |
| SQLAlchemy | 2.0.25 | **2.0.54** | 2.1.1 | Stay on 2.0.x LTS-like line: 2.1 removes/changes legacy behaviours and is a needless risk (GeoAlchemy2/Alembic interplay, no feature we need). Take latest 2.0 patch. |
| asyncpg | 0.29.0 | 0.31.0 | 0.31.0 | Current; PG18 verified. |
| Alembic | 1.13.1 | 1.20.0 | 1.20.0 | Current; migrations 001→007 apply cleanly on PG18. |
| GeoAlchemy2 | 0.14.3 | 0.20.0 | 0.20.0 | Current. |
| Celery (`[redis]`) | 5.3.6 | 5.6.3 | 5.6.3 | Current; redis-py resolved to 6.4.0 (Celery/kombu cap <7), kombu 5.6.2. |
| redis-py | 5.0.1 | 6.4.0 (via Celery) | 8.1.0 | Celery 5.6 constrains redis-py; do not force. |
| python-jose[cryptography] | 3.3.0 | 3.5.0 | 3.5.0 | Fixes known CVEs (algorithm confusion, JWE bomb). Long term: consider PyJWT (2.15.0). |
| cryptography | (transitive) | 50.0.1 (explicit) | 50.0.1 | Used directly (AES-GCM field encryption) so pinned explicitly. |
| argon2-cffi | 23.1.0 | 25.1.0 | 25.1.0 | Current. |
| pyotp / phonenumbers | 2.9.0 / 8.13.29 | 2.10.0 / 9.0.40 | 2.10.0 / 9.0.40 | Current. |
| firebase-admin | 6.4.0 | 7.7.0 | 7.7.0 | Current. **Breaking**: `messaging.send_multicast` removed → replaced by `send_each_for_multicast` (`app/services/push.py`). |
| structlog / ulid-py | 24.1.0 / 1.1.0 | 26.1.0 / 1.1.0 | 26.1.0 / 1.1.0 | Current. |
| pytest / pytest-asyncio / pytest-cov | 7.4.4 / 0.23.4 / 4.1.0 | 9.1.1 / 1.4.0 / 7.1.0 | same | Current (dev only). |
| httpx / factory-boy / faker | 0.26.0 / 3.3.0 / 22.5.1 | 0.28.1 / 3.3.3 / 40.39.0 | same | Dev only. |
| ruff / mypy / pre-commit | 0.2.1 / 1.8.0 / 3.6.0 | 0.16.9 / 2.3.1 / 4.6.2 | same | Dev only (not yet run — see UPGRADE_LOG). |

## 4. Infrastructure

| Component | Current | Selected | Latest Stable | Reason |
| --- | --- | --- | --- | --- |
| PostgreSQL + PostGIS | `postgis/postgis:16-3.4` (PG 16) | **`postgis/postgis:18-3.6`** (PG 18.6, PostGIS 3.6.4) | PG 18.6 (EOL 2030-11) | Newest major with 5 years support; async I/O gives better read throughput. Migrations + tests verified on it. Data volume needs dump/restore (documented in compose file). |
| Redis | `redis:7-alpine` | **`redis:8-alpine`** (8.10.2) | 8.10.2 | Current; compat with Celery 5.6 verified; `maxmemory 256mb` + `noeviction` (never evict broker keys). |
| App image | `python:3.12-slim` (+curl) | `python:3.12-slim`, no curl, stdlib healthcheck, single shared image tag | — | Smaller image; one build for api/worker/beat. |
| Celery worker/beat | unhealthy, no `-Q` | healthy; worker consumes all 6 routed queues; beat schedule in `/tmp` | — | See UPGRADE_LOG (functional fix). |
| Flower | compose profile, not installed in image | removed | 2.2.0 | Was non-functional (package not in requirements) and idle-RAM cost. |
| Docker Compose | `version`-less, fixed names | project-scoped names, 127.0.0.1-only ports, env-overridable ports | — | Allows side-by-side stacks; no accidental LAN exposure of DB/Redis. |
