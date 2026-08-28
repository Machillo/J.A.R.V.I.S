from __future__ import annotations

import os
from fastapi import APIRouter, Header, HTTPException, status

from backend.notifications.service import (
    get_vapid_public_key,
    notification_health,
    save_push_subscription,
    send_due_notifications,
    send_test_notification,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/status")
def notifications_status():
    return notification_health()


@router.get("/vapid-public-key")
def notifications_vapid_public_key():
    return get_vapid_public_key()


@router.post("/subscribe")
def notifications_subscribe(payload: dict):
    return save_push_subscription(payload)


@router.post("/test")
def notifications_test():
    return send_test_notification()


@router.post("/cron")
def notifications_cron(x_cron_secret: str | None = Header(default=None)):
    expected = os.getenv("NOTIFICATION_CRON_SECRET") or os.getenv("EMAIL_MONITOR_CRON_SECRET")
    if expected and x_cron_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cron secret inválido.")
    return send_due_notifications()
