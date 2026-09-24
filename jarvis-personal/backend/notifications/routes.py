from __future__ import annotations

import hmac
import os
from fastapi import APIRouter, Depends, Header, HTTPException, status

from backend.auth.current_user import require_roles

from backend.notifications.service import (
    get_vapid_public_key,
    notification_health,
    save_push_subscription,
    send_due_notifications,
    send_test_notification,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])
# Browser push is an Owner (JARVIS) feature; only /cron is public (secret-protected).
OWNER_ONLY = [Depends(lambda: require_roles("owner", "admin"))]


@router.get("/status", dependencies=OWNER_ONLY)
def notifications_status():
    return notification_health()


@router.get("/vapid-public-key", dependencies=OWNER_ONLY)
def notifications_vapid_public_key():
    return get_vapid_public_key()


@router.post("/subscribe", dependencies=OWNER_ONLY)
def notifications_subscribe(payload: dict):
    return save_push_subscription(payload)


@router.post("/test", dependencies=OWNER_ONLY)
def notifications_test():
    return send_test_notification()


@router.post("/cron")
def notifications_cron(x_cron_secret: str | None = Header(default=None)):
    expected = (os.getenv("NOTIFICATION_CRON_SECRET") or os.getenv("EMAIL_MONITOR_CRON_SECRET") or "").strip()
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="El cron de notificaciones no está configurado.")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cron secret inválido.")
    return send_due_notifications()
