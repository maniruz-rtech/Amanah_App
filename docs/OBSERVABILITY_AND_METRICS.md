# Observability and Metrics

## Goals

An emergency-response platform needs three classes of telemetry:

1. **Service health** — is the platform up, and if not, where?
2. **Business metrics** — alerts created per minute, time-to-acknowledge,
   delivery latency.
3. **Forensic audit** — for every emergency, can we reconstruct what
   happened?

The current implementation covers (1) and (3) end-to-end. (2) is wired
at the structural level (structlog emits the right field shapes) but
needs a metrics sink (Prometheus or DataDog) to be reportable. This is
the highest-priority observability gap.

## Service health — `/api/v1/health`

[backend/app/api/v1/health.py](../backend/app/api/v1/health.py) exposes:

```
GET /api/v1/health
{
  "status":      "healthy" | "degraded",
  "version":     "1.0.0",
  "environment": "dev",
  "timestamp":   "2026-05-22T00:16:30.902185+00:00",
  "services": {
    "database": { "up": true, "latency_ms": 2.92, "error": null },
    "redis":    { "up": true, "latency_ms": 2.97, "error": null }
  }
}
```

Notes:

- Always returns 200; the `status` field is the operator signal.
- Latency reported per subsystem so a slow DB shows up before it
  affects the request path.
- `error` field is truncated to 200 chars and intentionally returns the
  underlying exception message — useful for first-line ops triage.

For Kubernetes / LB-style probes:

- `GET /api/v1/ready` returns **503** when DB or Redis is down (so the
  probe fails closed).
- `GET /api/v1/live` returns **200** unconditionally, never touches I/O
  (lightweight liveness).

## Structured logging

Backend uses `structlog`. Every request carries a `request_id` bound via
middleware in `app/main.py`:

```python
structlog.contextvars.bind_contextvars(request_id=request_id)
```

Useful queries against the production log sink:

```
event:"sos_created" AND user_id:"usr_..."
event:"login_success" AND status_code:200
event:"ws_v2_connected"
event:"readiness_failed"
event:"fcm_emergency_failed"
```

All emitted with `await logger.ainfo(...)` so they're non-blocking.

Sample event shapes:

```json
{ "event": "sos_created",        "user_id": "usr_...", "incident_id": "inc_..." }
{ "event": "login_success",      "user_id": "usr_..." }
{ "event": "request_completed",  "method": "POST", "path": "/api/v1/incidents/sos", "status_code": 201, "process_time_ms": 70.51 }
{ "event": "ws_v2_connected",    "user_id": "usr_..." }
{ "event": "fcm_emergency_sent", "alert_id": "inc_...", "success": 12, "failed": 0 }
{ "event": "readiness_failed",   "db_up": false, "redis_up": true }
```

## Business metrics (recommended Prometheus export)

Add `prometheus-fastapi-instrumentator` to `backend/requirements.txt`
and mount in `app/main.py`:

```python
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

This gives you for free:

- `http_requests_total{method,endpoint,status}` — request volume
- `http_request_duration_seconds_bucket{...}` — latency histogram

For Amanah-specific metrics, add a tiny `metrics.py`:

```python
from prometheus_client import Counter, Histogram, Gauge

sos_created_total       = Counter("amanah_sos_created_total", "SOS incidents created")
sos_persist_latency_sec = Histogram("amanah_sos_persist_latency_seconds",
                                     "Time from POST receipt to DB commit",
                                     buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 5))
ws_active_connections   = Gauge("amanah_ws_active_connections", "Currently connected WS clients")
fcm_push_failures_total = Counter("amanah_fcm_push_failures_total", "FCM push failures", ["reason"])
```

And instrument the hot paths:

```python
async def create_sos(self, ...):
    with sos_persist_latency_sec.time():
        incident = await self.incident_repo.create_sos(...)
    sos_created_total.inc()
    ...
```

SLO targets:

| Metric | Target |
|---|---|
| `amanah_sos_persist_latency_seconds` p95 | < 200 ms |
| `amanah_fcm_push_failures_total / total` | < 1 % over 1h |
| `amanah_ws_active_connections` drop > 50% in 60s | alert |
| `http_request_duration_seconds_bucket{endpoint="/api/v1/incidents/sos"}` p95 | < 500 ms |

## Client-side telemetry

The Android client has hooks but no sink yet:

- `OkHttpRealtimeGateway` has a `logger: (String) -> Unit` callback
  surfaced via `AppGraph`. In debug it logs to `Log.d`. In release,
  point it at Sentry breadcrumbs:

  ```kotlin
  OkHttpRealtimeGateway(
      ...,
      logger = { msg -> Sentry.addBreadcrumb(Breadcrumb(msg).apply { category = "realtime" }) },
  )
  ```

- `AmanahDebugDrawer` already records state changes; in production
  point its sink at the same Sentry breadcrumb buffer.

- `EmergencyAlertEngine`'s `onAlertPersisted` / `onAlertError` callbacks
  are perfect Sentry breadcrumb sources.

## Audit visibility

Every privileged action writes to `audit_logs` (server-side). The admin
dashboard already exposes the data via `/api/v1/admin/audit-logs`. For
operator-facing visibility add a simple Grafana panel:

```sql
SELECT action, count(*)
FROM audit_logs
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY action
ORDER BY count(*) DESC;
```

## Tracing

OpenTelemetry instrumentation isn't wired yet. When you add it, the
critical spans to capture:

- `POST /incidents/sos` end-to-end (request → DB commit → WS broadcast → push fanout)
- The WS handshake (DNS → TLS → upgrade → auth.accepted)
- Each FCM dispatch

The structlog `request_id` already provides cross-component correlation
for HTTP requests; OTEL would extend that to async tasks (Celery, FCM
SDK).

## Realtime monitoring dashboard

Minimal Grafana panel set:

1. **Health** — `/api/v1/health` status, DB/Redis latency over time.
2. **SOS throughput** — `amanah_sos_created_total` rate per 5min.
3. **Persist latency** — `amanah_sos_persist_latency_seconds` p50/p95/p99.
4. **WS connections** — `amanah_ws_active_connections` over time.
5. **FCM failures** — `amanah_fcm_push_failures_total` by reason.
6. **Audit volume** — count of `audit_logs` rows per minute by action.

## Alerts

| Severity | Condition | Notify |
|---|---|---|
| P1 | `/api/v1/ready` returns 503 for > 30 s | PagerDuty oncall |
| P1 | SOS persistence latency p95 > 1 s for > 60 s | PagerDuty oncall |
| P2 | WS active connections drop > 50 % in 60 s | Slack #amanah-ops |
| P2 | FCM failure rate > 5 % over 5 min | Slack #amanah-ops |
| P3 | Audit-log write rate drops to 0 for > 5 min | Slack #amanah-ops |
