from __future__ import annotations

import hashlib
import hmac
import os
import base64
import time
from fastapi import APIRouter, Header, HTTPException, Request

from backend.deployment_monitor.service import deployment_summary, save_event
from backend.auth.current_user import get_current_user

router = APIRouter(prefix="/deployment-monitor", tags=["Deployment monitor"])


def _check_secret(raw: bytes, provider: str, supplied: str | None) -> None:
    secret = os.getenv("DEPLOYMENT_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(503, "Falta DEPLOYMENT_WEBHOOK_SECRET.")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(403, f"Firma {provider} inválida.")


def _check_render_signature(raw: bytes, webhook_id: str | None, webhook_timestamp: str | None, signature: str | None) -> None:
    secret = os.getenv("RENDER_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(503, "Falta RENDER_WEBHOOK_SECRET.")
    if not webhook_id or not webhook_timestamp or not signature:
        raise HTTPException(403, "Firma Render incompleta.")
    try:
        if abs(time.time() - int(webhook_timestamp)) > 300:
            raise HTTPException(403, "Webhook Render vencido.")
        key = base64.b64decode(secret.removeprefix("whsec_"))
        signed = webhook_id.encode() + b"." + webhook_timestamp.encode() + b"." + raw
        expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(403, "No se pudo validar la firma Render.") from exc
    supplied_values = [part.strip().removeprefix("v1,") for part in signature.split()]
    if not any(hmac.compare_digest(expected, value) for value in supplied_values):
        raise HTTPException(403, "Firma Render inválida.")


@router.get("")
def deployments():
    # Defense in depth: this endpoint is also protected by main.auth_middleware.
    get_current_user()
    return deployment_summary()


@router.post("/webhook/{provider}")
async def deployment_webhook(
    request: Request,
    provider: str,
    x_hub_signature_256: str | None = Header(default=None),
    webhook_id: str | None = Header(default=None),
    webhook_timestamp: str | None = Header(default=None),
    webhook_signature: str | None = Header(default=None),
):
    if provider not in {"github", "vercel", "render"}:
        raise HTTPException(400, "Proveedor no soportado en este endpoint.")
    raw = await request.body()
    if provider == "render":
        _check_render_signature(raw, webhook_id, webhook_timestamp, webhook_signature)
    else:
        _check_secret(raw, provider, x_hub_signature_256)
    event = save_event(provider, await request.json())
    return {"status": "OK", "event_id": event.get("id")}
