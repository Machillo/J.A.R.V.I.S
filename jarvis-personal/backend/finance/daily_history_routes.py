import hmac
import os

from fastapi import APIRouter, Header, HTTPException, status

from backend.core import observability
from backend.finance.daily_history import run_daily_financial_history

router = APIRouter(prefix="/financial-history", tags=["Financial history"])


@router.post("/cron")
def financial_history_cron(x_cron_secret: str | None = Header(default=None)):
    """The daily financial-history job (P0.2). Secret-protected like /notifications/cron.

    The external scheduler decides when to call it; the workspaces come from the server.
    """
    expected = (os.getenv("NOTIFICATION_CRON_SECRET") or os.getenv("EMAIL_MONITOR_CRON_SECRET") or "").strip()
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="El cron de historial financiero no está configurado.")
    # Bytes, so a non-ASCII header is a plain mismatch (403), never a TypeError (500).
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cron secret inválido.")
    try:
        result = run_daily_financial_history()
    except Exception as exc:
        observability.heartbeat("financial_history", ok=False, error_class=type(exc).__name__)
        raise
    if result["status"] == "ALREADY_RUNNING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El historial financiero ya se está registrando.")
    observability.heartbeat("financial_history", ok=result["failed"] == 0,
                            error_class=None if result["failed"] == 0 else "workspace_failures")
    return result
