from __future__ import annotations

import threading
from collections import OrderedDict

from fastapi import HTTPException, Request

from backend.auth.current_user import get_current_account_id
from backend.core.database import get_connection


TERMS_VERSION = "2026-09-23-v3"
PRIVACY_VERSION = "2026-09-25-v4"


def legal_status(conn, account_id: str) -> dict:
    row = conn.execute(
        """SELECT terms_accepted_at,privacy_accepted_at
           FROM legal_acceptances
           WHERE account_id=%s AND terms_version=%s AND privacy_version=%s
           ORDER BY created_at DESC LIMIT 1""",
        (account_id, TERMS_VERSION, PRIVACY_VERSION),
    ).fetchone()
    return {
        "required": row is None,
        "terms_version": TERMS_VERSION,
        "privacy_version": PRIVACY_VERSION,
        "accepted_at": (row or {}).get("terms_accepted_at"),
    }


# SEC-01: a signed-in user who has not accepted the current Terms and Privacy Policy may only
# read their identity (which says `legal.required`), accept, use their privacy rights (export,
# deletion) and reach support, plus the read-only operational state the apps load. Everything
# else answers 403 `legal_acceptance_required` until they accept. Public paths (health, release
# policy, webhooks, crons) never reach this check. The Owner is not a commercial user: its
# behavior is unchanged (decision V1-5a), as in the apps and the web lab.
LEGAL_REQUIRED_CODE = "legal_acceptance_required"
ROUTES_BEFORE_ACCEPTANCE = frozenset({
    ("GET", "/auth/me"),
    ("DELETE", "/auth/me"),
    ("GET", "/auth/me/export"),
    ("POST", "/auth/legal/accept"),
    ("GET", "/product-ops/feature-flags"),
    ("GET", "/product-ops/health"),
    ("GET", "/product-ops/feedback"),
    ("POST", "/product-ops/feedback"),
})

# Accounts known to have accepted the current versions. An acceptance is never withdrawn for a
# version (a new version changes the key), so a positive answer can be remembered; a missing one
# is always read again, so accepting takes effect on the next request.
_ACCEPTED_LIMIT = 10_000
_accepted: OrderedDict[tuple[str, str, str], None] = OrderedDict()
_accepted_lock = threading.Lock()


def _has_accepted(account_id: str) -> bool:
    key = (account_id, TERMS_VERSION, PRIVACY_VERSION)
    with _accepted_lock:
        if key in _accepted:
            _accepted.move_to_end(key)
            return True
    with get_connection() as conn:
        accepted = not legal_status(conn, account_id)["required"]
    if accepted:
        with _accepted_lock:
            _accepted[key] = None
            while len(_accepted) > _ACCEPTED_LIMIT:
                _accepted.popitem(last=False)
    return accepted


def acceptance_required(user: dict, method: str, path: str) -> bool:
    """Whether this authenticated request must wait for the legal acceptance (SEC-01)."""
    if user.get("role") == "owner":
        return False
    if (method.upper(), path.rstrip("/") or "/") in ROUTES_BEFORE_ACCEPTANCE:
        return False
    account_id = user.get("account_id")
    if not account_id:
        return True  # fail closed: no account, nothing but the routes above
    return not _has_accepted(str(account_id))


def acceptance_required_detail() -> dict:
    from backend.core.i18n import current_language

    message = ("Antes de continuar, aceptá los Términos y la Política de Privacidad vigentes."
               if current_language() == "es" else
               "Before continuing, accept the current Terms and Privacy Policy.")
    return {"code": LEGAL_REQUIRED_CODE, "message": message}


def forget_acceptances() -> None:
    """Tests only: start from an empty memory of acceptances."""
    with _accepted_lock:
        _accepted.clear()


def accept_legal_documents(payload, request: Request) -> dict:
    if not payload.accept_terms or not payload.accept_privacy:
        raise HTTPException(422, "Debés aceptar los Términos y la Política de Privacidad para continuar.")
    if payload.terms_version != TERMS_VERSION or payload.privacy_version != PRIVACY_VERSION:
        raise HTTPException(409, "Los documentos cambiaron. Leé y aceptá la versión vigente.")

    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    ip_address = forwarded or (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent", "")[:500] or None
    account_id = get_current_account_id()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO legal_acceptances(
                 account_id,terms_version,privacy_version,terms_accepted_at,privacy_accepted_at,ip_address,user_agent
               ) VALUES(%s,%s,%s,NOW(),NOW(),%s,%s)
               ON CONFLICT(account_id,terms_version,privacy_version) DO NOTHING""",
            (account_id, TERMS_VERSION, PRIVACY_VERSION, ip_address, user_agent),
        )
        conn.commit()
        return {"status": "accepted", **legal_status(conn, account_id)}
