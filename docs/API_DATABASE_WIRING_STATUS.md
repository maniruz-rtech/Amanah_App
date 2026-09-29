# API ↔ Database Wiring Status

Per-endpoint inventory. Each row is verified by reading the code, not by
assumption. "Persists" means the endpoint's service path includes a real
SQL mutation; "Reads" means it issues a real `SELECT`.

---

## Auth & Identity

| Endpoint | Method | Status | DB action |
|---|---|---|---|
| `/api/v1/auth/login` | POST | ✅ Persists + reads | SELECT `users` by username/email + `users.failed_login_attempts` UPDATE; INSERT `refresh_tokens`; INSERT `audit_logs` |
| `/api/v1/auth/refresh` | POST | ✅ Persists + reads | SELECT `refresh_tokens` by token (hash recommended); INSERT new `refresh_tokens` row; soft-delete old |
| `/api/v1/auth/logout` | POST | ✅ Persists | DELETE `refresh_tokens` for current token |
| `/api/v1/auth/logout/all` | POST | ✅ Persists | DELETE all `refresh_tokens` for `user_id` |
| `/api/v1/auth/mfa/setup` | POST | ✅ Persists | UPDATE `users.mfa_secret` |
| `/api/v1/auth/mfa/confirm` | POST | ✅ Persists | UPDATE `users.mfa_enabled = true` |
| `/api/v1/auth/mfa/verify` | POST | ✅ Reads | SELECT `users.mfa_secret`; INSERT `refresh_tokens` |
| `/api/v1/auth/otp/request` | POST | ✅ Persists | INSERT `otp_requests` |
| `/api/v1/auth/otp/verify` | POST | ✅ Persists | UPDATE `otp_requests`; UPDATE `users.is_verified` |
| `/api/v1/auth/password-reset/request` | POST | ✅ Persists | INSERT `password_reset_requests` + INSERT `admin_approvals` |
| `/api/v1/auth/password-reset/complete` | POST | ✅ Persists | UPDATE `users.password_hash`; UPDATE `password_reset_requests` |

## OTP

| Endpoint | Method | Status | DB action |
|---|---|---|---|
| `/api/v1/otp/request` | POST | ✅ Persists | INSERT `otp_requests` |
| `/api/v1/otp/verify` | POST | ✅ Persists | UPDATE `otp_requests` |
| `/api/v1/otp/status` | POST | ✅ Reads | SELECT `otp_requests` |
| `/api/v1/otp/resend` | POST | ✅ Persists | UPDATE/INSERT `otp_requests` |

## Users

| Endpoint | Method | Status | DB action |
|---|---|---|---|
| `/api/v1/users/me` | GET | ✅ Reads | SELECT `users` joined with `user_roles`, `devices`, `trusted_contacts` |
| `/api/v1/users/me` | PATCH | ✅ Persists | UPDATE `users` |
| `/api/v1/users/devices` | POST | ✅ Persists | INSERT `devices` (FCM token registration) |
| `/api/v1/users/devices` | GET | ✅ Reads | SELECT `devices` for user |
| `/api/v1/users/devices/{id}` | DELETE | ✅ Persists | DELETE `devices` (revoke) |
| `/api/v1/users/devices/sync-fcm` | POST | ✅ Persists | UPDATE `devices.fcm_token` |
| `/api/v1/users/trusted-contacts` | GET | ✅ Reads | SELECT `trusted_contacts` for user |
| `/api/v1/users/trusted-contacts` | POST | ✅ Persists | INSERT `trusted_contacts` |
| `/api/v1/users/trusted-contacts/{id}` | PATCH | ✅ Persists | UPDATE `trusted_contacts` |
| `/api/v1/users/trusted-contacts/{id}` | DELETE | ✅ Persists | DELETE `trusted_contacts` |
| **`/api/v1/users/nearby`** | GET | ❌ **does not exist** | needed by Android Home tab |

## Incidents (SOS)

| Endpoint | Method | Status | DB action |
|---|---|---|---|
| `/api/v1/incidents/sos` | POST | ✅ Persists | INSERT `incidents` + INSERT `emergency_locations` (PostGIS) + INSERT `incident_events` + INSERT `audit_logs` |
| `/api/v1/incidents/my/active` | GET | ✅ Reads | SELECT `incidents` filtered by `created_by_id` + status set |
| `/api/v1/incidents/{id}` | GET | ✅ Reads | SELECT `incidents` joined with relations (creator, region, locations, assignments, events) |
| `/api/v1/incidents/{id}/location` | POST | ✅ Persists | INSERT `emergency_locations` + INSERT `incident_events` |
| `/api/v1/incidents/{id}/cancel` | POST | ✅ Persists | UPDATE `incidents.status = CANCELLED` + INSERT `incident_events` |
| `/api/v1/incidents/{id}/resolve` | POST | ✅ Persists | UPDATE `incidents.status = RESOLVED` + INSERT `incident_events` |

## Responders

| Endpoint | Method | Status | DB action |
|---|---|---|---|
| `/api/v1/responders/me/status` | GET | ✅ Reads | SELECT `responder_status` |
| `/api/v1/responders/me/status` | PUT | ✅ Persists | UPSERT `responder_status` |
| `/api/v1/responders/me/assignments` | GET | ✅ Reads | SELECT `incident_assignments` filtered by `responder_id` |
| `/api/v1/responders/assignments/{id}/accept` | POST | ✅ Persists | UPDATE `incident_assignments` + INSERT `incident_events` |
| `/api/v1/responders/assignments/{id}/decline` | POST | ✅ Persists | UPDATE `incident_assignments` + INSERT `incident_events` |
| `/api/v1/responders/assignments/{id}/en-route` | POST | ✅ Persists | UPDATE `incident_assignments` + INSERT `incident_events` |
| `/api/v1/responders/assignments/{id}/arrived` | POST | ✅ Persists | UPDATE `incident_assignments` + INSERT `incident_events` |
| `/api/v1/responders/assignments/{id}/complete` | POST | ✅ Persists | UPDATE `incident_assignments` + INSERT `incident_events` |
| `/api/v1/responders/nearby` | GET | ✅ Reads | SELECT `responder_status` + PostGIS ST_DWithin |

## Notifications

| Endpoint | Method | Status | DB action |
|---|---|---|---|
| `/api/v1/notifications` | GET | ✅ Reads | SELECT `notifications` paginated |
| `/api/v1/notifications/mark-read` | POST | ✅ Persists | UPDATE `notifications.read = true` |
| `/api/v1/notifications/mark-all-read` | POST | ✅ Persists | UPDATE `notifications` for user |
| `/api/v1/notifications/unread-count` | GET | ✅ Reads | SELECT COUNT |

## Admin

| Endpoint | Method | Status | DB action |
|---|---|---|---|
| `/api/v1/admin/users` | GET | ✅ Reads | SELECT `users` paginated |
| `/api/v1/admin/users/{id}` | GET | ✅ Reads | SELECT `users` with relations |
| `/api/v1/admin/users` | POST | ✅ Persists | INSERT `users` |
| `/api/v1/admin/users/{id}/approve` | POST | ✅ Persists | UPDATE `users.is_verified` + INSERT `audit_logs` |
| `/api/v1/admin/users/{id}/suspend` | POST | ✅ Persists | UPDATE `users.is_suspended` + INSERT `audit_logs` |
| `/api/v1/admin/users/{id}` | DELETE | ✅ Persists | Soft-delete `users` |
| `/api/v1/admin/audit-logs` | GET | ✅ Reads | SELECT `audit_logs` filtered |
| `/api/v1/admin/approvals` | GET | ✅ Reads | SELECT `admin_approvals` pending |
| `/api/v1/admin/approvals/{id}` | POST | ✅ Persists | UPDATE `admin_approvals` |
| `/api/v1/admin/organizations` | GET | ✅ Reads | SELECT `organizations` |
| `/api/v1/admin/regions` | GET | ✅ Reads | SELECT `regions` |
| `/api/v1/admin/roles` | GET | ✅ Reads | SELECT `roles` |

## WebSocket (`/ws` and `/ws-legacy`)

| Channel | Inbound persistence | Outbound trigger | Verdict |
|---|---|---|---|
| `ping` / `pong` | None — heartbeat | n/a | ✅ correct |
| `ack` | None | n/a | ✅ correct |
| `auth.accepted` | None | Server emits after handshake | ✅ correct |
| **`emergency.alert`** | ❌ TODO — `_handle_emergency_alert` is a log-only stub | Server emits when REST `/incidents/sos` persists | ⚠️ **lossy if client uses WS path** |
| `responder.location` | ⚠️ Fans out via `ConnectionManager.broadcast_location_update` but does NOT INSERT into `emergency_locations`. Only REST `/incidents/{id}/location` persists. | Same | ⚠️ **lossy if responder pushes via WS** |
| `presence` | ❌ TODO — log only | n/a | Should UPSERT `users.last_h3_cell_*` + `users.last_seen_at` |
| `admin.notification` | n/a — server only sends | Server emits on approve/suspend | ✅ correct |

---

## Persistence guarantees

- **REST writes** are inside the `get_db()` transaction → either all rows commit
  or all roll back. ✅
- **WS writes** currently do not occur. ❌
- **No two-phase commit needed** — the WS broadcast happens after the REST
  transaction commits, so there's no risk of broadcasting an event whose DB
  record disappeared.

## What Android currently calls

Cross-reference with the persistence inventory above:

| Android code path | Calls API? | Notes |
|---|---|---|
| `AuthRepository.login` | ✅ `POST /api/v1/auth/login` | only real wiring today |
| Everything else | ❌ | All hard-coded fixtures |

So the gap is: 60+ endpoints persist correctly on the backend, but the Android
client only uses 1 of them. **The fix is mostly client-side, not server-side.**
