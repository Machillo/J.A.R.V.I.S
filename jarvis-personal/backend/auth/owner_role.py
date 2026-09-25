"""The internal Owner role (DINCR Owner / JARVIS) is explicit, never inferred.

- The stored role (allowed_users.role / accounts.role) is the source of truth.
  Login never writes it, so no configuration change can promote or demote
  anyone. Granting or revoking the Owner role is an explicit, reviewed command
  (backend/scripts/set_owner_role.py).
- OWNER_EMAILS is a second, deployment-level key: a stored Owner is honored only
  while its email is listed. Removing an email removes Owner access at once
  (no eternal privileges). A missing or transiently wrong value refuses the
  Owner login instead of downgrading it to a User: nothing is written, and the
  Owner is back as soon as the configuration is.
- Being listed never makes a User an Owner.
"""
from __future__ import annotations

import logging
import os

from fastapi import HTTPException

logger = logging.getLogger(__name__)

OWNER_ROLE = "owner"
OWNER_NOT_ENABLED = "Esta cuenta interna no está habilitada en este entorno."


def owner_allowlist() -> frozenset[str]:
    """Emails allowed to act as Owner in this deployment (read at call time)."""
    return frozenset(email.strip().lower() for email in os.getenv("OWNER_EMAILS", "").split(",") if email.strip())


def owner_enabled(email: str | None) -> bool:
    return bool(email) and str(email).strip().lower() in owner_allowlist()


def enabled_owner_email(conn) -> str:
    """The single stored Owner that this deployment also lists; fail closed otherwise.

    For Owner-only background integrations that must pick "the Owner" without a
    session: being listed alone never qualifies (a listed User is not an Owner).
    """
    rows = conn.execute(
        "SELECT email FROM allowed_users WHERE role=%s AND status='active'", (OWNER_ROLE,)
    ).fetchall() or []
    enabled = sorted({str(row["email"]).strip().lower() for row in rows if owner_enabled(row.get("email"))})
    if len(enabled) != 1:
        raise RuntimeError("No hay exactamente un Owner habilitado en este entorno.")
    return enabled[0]


def session_role(stored_role: str | None, email: str | None) -> str:
    """Role for a path that must not fail (finishing a deletion): an ungated Owner is a User there."""
    return stored_role if stored_role != OWNER_ROLE or owner_enabled(email) else "user"


def effective_role(stored_role: str | None, email: str | None, *, account_ref: object = None) -> str:
    """The role a session gets: the stored one, with the Owner role gated by the allowlist."""
    if stored_role != OWNER_ROLE:
        return stored_role or "user"
    if owner_enabled(email):
        return OWNER_ROLE
    # Fail closed without demoting: no Owner session, no User session, no write.
    logger.warning("Owner login refused: the account is not in this deployment's Owner allowlist")
    raise HTTPException(status_code=403, detail=OWNER_NOT_ENABLED)
