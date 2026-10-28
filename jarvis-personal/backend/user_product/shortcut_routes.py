"""iOS Shortcuts routes (VIP and the Owner).

- ``/token`` (GET/POST/DELETE): the app's normal session links, checks or unlinks Shortcuts.
- ``/apple-pay`` and ``/bank-sms``: called by the App Intents with the Shortcuts token only.
  They are public paths for the session middleware (no app session in a background intent),
  so this module does what the middleware does for a session: authenticate the token, apply
  the legal acceptance and the write limit, check the plan, then capture.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, Response

from backend.auth.current_user import reset_current_user, set_current_user
from backend.auth.legal import acceptance_required, acceptance_required_detail
from backend.auth.saas import require_feature
from backend.core import write_limit
from backend.user_product import shortcut_capture, shortcut_tokens

PREFIX = "/user-product/vip/shortcuts"
router = APIRouter(prefix=PREFIX, tags=["DINCR Shortcuts"])
# The capture routes authenticate with the Shortcuts token (main.PUBLIC_PATHS).
CAPTURE_PATHS = frozenset({f"{PREFIX}/apple-pay", f"{PREFIX}/bank-sms"})


@router.get("/token")
def shortcuts_status():
    require_feature("ios_shortcuts")
    return shortcut_tokens.link_status()


@router.post("/token")
def shortcuts_link():
    require_feature("ios_shortcuts")
    return shortcut_tokens.issue_token()


@router.delete("/token")
def shortcuts_unlink():
    # Unlinking is always allowed (sign-out, a plan that ended): no plan check.
    return shortcut_tokens.revoke_token()


def _captured(path: str, authorization: str | None, idempotency_key: str | None, body: dict[str, Any],
              response: Response, capture) -> dict[str, Any]:
    user = shortcut_tokens.authenticate(authorization)
    token = set_current_user(user)
    try:
        if acceptance_required(user, "POST", path):
            raise HTTPException(status_code=403, detail=acceptance_required_detail())
        retry_after = write_limit.retry_after_for(user, "POST", path)
        if retry_after is not None:
            raise HTTPException(status_code=429, detail="Demasiados envíos seguidos. Intentá de nuevo en unos segundos.",
                                headers={"Retry-After": str(int(retry_after + 0.999))})
        require_feature("ios_shortcuts")
        result = capture(user, body if isinstance(body, dict) else {}, idempotency_key)
    finally:
        reset_current_user(token)
    response.status_code = 201 if result.get("status") == "created" else 200
    return result


@router.post("/apple-pay", status_code=201)
def shortcuts_apple_pay(response: Response, body: dict[str, Any] = Body(...),
                        authorization: str | None = Header(default=None),
                        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return _captured(f"{PREFIX}/apple-pay", authorization, idempotency_key, body, response,
                     shortcut_capture.capture_apple_pay)


@router.post("/bank-sms", status_code=201)
def shortcuts_bank_sms(response: Response, body: dict[str, Any] = Body(...),
                       authorization: str | None = Header(default=None),
                       idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return _captured(f"{PREFIX}/bank-sms", authorization, idempotency_key, body, response,
                     shortcut_capture.capture_bank_sms)
