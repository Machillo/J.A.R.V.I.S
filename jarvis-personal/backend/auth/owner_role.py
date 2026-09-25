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


def effective_role(stored_role: str | None, email: str | None, *, account_ref: object = None) -> str:
    """The role a session gets: the stored one, with the Owner role gated by the allowlist."""
    if stored_role != OWNER_ROLE:
        return stored_role or "user"
    if owner_enabled(email):
        return OWNER_ROLE
    # Fail closed without demoting: no Owner session, no User session, no write.
    logger.warning("Owner login refused: the account is not in this deployment's Owner allowlist ref=%s", account_ref)
    raise HTTPException(status_code=403, detail=OWNER_NOT_ENABLED)
