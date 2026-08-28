import hmac
import os

from fastapi import Header, HTTPException, status


ADMIN_API_KEY = os.getenv("JARVIS_ADMIN_API_KEY", "").strip()


def require_admin_api_key(x_jarvis_admin_key: str | None = Header(default=None)) -> None:
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="JARVIS_ADMIN_API_KEY no está configurada.")
    if not x_jarvis_admin_key or not hmac.compare_digest(x_jarvis_admin_key, ADMIN_API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credencial administrativa inválida.")
