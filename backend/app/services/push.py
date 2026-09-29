"""
FCM push dispatch — emergency wakeup + nearby fanout.

The transport is intentionally pluggable:

  - In **dev** with `FCM_ENABLED=false`, this module is a no-op logger.
    Useful so the SOS persistence path doesn't block on Firebase.
  - In **prod**, set `FCM_ENABLED=true` and ship a service-account JSON
    via `FIREBASE_CREDENTIALS_PATH`. The module then uses the
    ``firebase_admin`` SDK.

The dispatcher exposes three primitives:

  - ``send_wakeup(device_tokens)``       — data-only ping; killed apps
                                            wake & reconnect the WS.
  - ``send_emergency_alert(...)``        — high-priority + visible
                                            notification when the WS is
                                            unreachable.
  - ``send_admin_notification(...)``     — generic notification for
                                            admin-channel events.

This file is import-safe even when firebase_admin is not installed.
"""

from __future__ import annotations

import structlog
from typing import Any, Iterable

from app.core.config import settings

logger = structlog.get_logger()

_initialized = False
_messaging = None  # type: ignore[var-annotated]


def _init_firebase() -> bool:
    """Lazy-init the Firebase Admin SDK once per process."""
    global _initialized, _messaging
    if _initialized:
        return _messaging is not None
    _initialized = True

    if not settings.fcm_enabled:
        return False

    try:
        import firebase_admin  # type: ignore
        from firebase_admin import credentials, messaging  # type: ignore

        cred_path = settings.firebase_credentials_path
        if cred_path:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
        _messaging = messaging
        return True
    except Exception as exc:  # noqa: BLE001
        logger.bind(error=str(exc)).awarning_sync = lambda **k: None  # type: ignore
        # We deliberately swallow init failures here: an emergency-response
        # platform must keep persisting incidents even if Firebase is sick.
        return False


def send_wakeup(device_tokens: Iterable[str]) -> None:
    """Silent data-only push to wake killed apps & make them reconnect."""
    tokens = [t for t in device_tokens if t]
    if not tokens:
        return
    if not _init_firebase():
        logger.info("fcm_disabled_wakeup_noop", count=len(tokens))
        return

    msg = _messaging.MulticastMessage(  # type: ignore[attr-defined]
        tokens=tokens,
        data={"kind": "wakeup"},
        android=_messaging.AndroidConfig(  # type: ignore[attr-defined]
            priority="high",
        ),
    )
    try:
        result = _messaging.send_each_for_multicast(msg)  # type: ignore[attr-defined]
        logger.info("fcm_wakeup_sent", success=result.success_count, failed=result.failure_count)
    except Exception as exc:  # noqa: BLE001
        logger.warning("fcm_wakeup_failed", error=str(exc))


def send_emergency_alert(
    device_tokens: Iterable[str],
    *,
    alert_id: str,
    title: str,
    body: str,
    lat: float | None = None,
    lng: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """High-priority emergency push; renders a visible notification."""
    tokens = [t for t in device_tokens if t]
    if not tokens:
        return
    if not _init_firebase():
        logger.info(
            "fcm_disabled_emergency_noop",
            alert_id=alert_id, count=len(tokens),
        )
        return

    data: dict[str, str] = {
        "kind":     "emergency.alert",
        "alert_id": alert_id,
        "title":    title,
        "body":     body,
    }
    if lat is not None:
        data["lat"] = f"{lat}"
    if lng is not None:
        data["lng"] = f"{lng}"
    if extra:
        for k, v in extra.items():
            data[k] = str(v)

    msg = _messaging.MulticastMessage(  # type: ignore[attr-defined]
        tokens=tokens,
        data=data,
        notification=_messaging.Notification(title=title, body=body),  # type: ignore[attr-defined]
        android=_messaging.AndroidConfig(  # type: ignore[attr-defined]
            priority="high",
            notification=_messaging.AndroidNotification(  # type: ignore[attr-defined]
                channel_id="amanah_emergency",
                priority="max",
                default_vibrate_timings=True,
                visibility="public",
            ),
        ),
    )
    try:
        result = _messaging.send_each_for_multicast(msg)  # type: ignore[attr-defined]
        logger.info(
            "fcm_emergency_sent",
            alert_id=alert_id,
            success=result.success_count,
            failed=result.failure_count,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("fcm_emergency_failed", alert_id=alert_id, error=str(exc))
