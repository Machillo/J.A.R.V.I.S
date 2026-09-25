"""Plan changes that respect the access the account already has.

Terms (account_subscriptions is the entitlement DINCR enforces):
- current plan / entitlement: ``plan_id`` while the row is active and, for a
  time-bounded grant, until its end;
- entitlement end: a courtesy grant's ``expires_at`` (the launch promotion is a
  courtesy) or an off-store paid period's ``billing_subscriptions.current_period_end``;
- pending change: ``pending_plan_id`` takes effect at ``pending_effective_at``
  (the entitlement end). Until then the current plan keeps every benefit.

Rules:
- upgrade: immediate, through the existing activation paths; clears any pending change;
- downgrade or cancellation with a future entitlement end: scheduled, never immediate;
- choosing the current plan again while a change is pending: keeps the plan (undo);
- store-managed subscriptions (App Store / Google Play): only the store's verified
  events change them, so a request here is refused rather than simulated;
- at the end of the entitlement the pending plan applies when it is Free or is
  covered by an active payment; otherwise the account falls back to Free.

Nothing here assumes a trial or promotion length: every date is the stored one.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import HTTPException

from backend.core.schema_state import columns_exist, tables_exist

PLAN_RANK = {"free": 1, "basic": 2, "vip": 3}
PENDING_COLUMNS = ("pending_plan_id", "pending_effective_at", "pending_requested_at")
STORE_ACTIVE_STATES = ("trialing", "active", "grace_period")
# The columns are only ever added (and, on rollback, dropped with a backend
# restart), so a positive answer is reused briefly instead of asking the catalog
# several times per request.
_SUPPORTED_TTL_SECONDS = 300
_supported_until = 0.0


def pending_supported(conn) -> bool:
    global _supported_until
    if time.monotonic() < _supported_until:
        return True
    if columns_exist(conn, "account_subscriptions", PENDING_COLUMNS):
        _supported_until = time.monotonic() + _SUPPORTED_TTL_SECONDS
        return True
    return False


def lock_billing_then_subscription(conn, account_id: str) -> None:
    """Take the two rows every plan transition may write, always in this order.

    The lazy expiry of a paid period writes billing_subscriptions and then
    account_subscriptions; every other transition locks them in the same order,
    so two requests of one account cannot deadlock.
    """
    conn.execute("SELECT 1 FROM billing_subscriptions WHERE account_id=%s FOR UPDATE", (account_id,))
    conn.execute("SELECT 1 FROM account_subscriptions WHERE account_id=%s FOR UPDATE", (account_id,))


def clear_pending(conn, account_id: str) -> None:
    """Drop a scheduled change (an upgrade, a new grant or an admin action replaces it)."""
    if pending_supported(conn):
        conn.execute(
            """UPDATE account_subscriptions
               SET pending_plan_id=NULL,pending_effective_at=NULL,pending_requested_at=NULL
               WHERE account_id=%s AND pending_plan_id IS NOT NULL
               RETURNING id""",
            (account_id,),
        )


def pending_change(conn, account_id: str) -> dict | None:
    if not pending_supported(conn):
        return None
    row = conn.execute(
        """SELECT p.code AS pending_plan, s.pending_effective_at
           FROM account_subscriptions s JOIN plans p ON p.id=s.pending_plan_id
           WHERE s.account_id=%s""",
        (account_id,),
    ).fetchone()
    if not row:
        return None
    from backend.product_ops.service import has_active_payment

    change = dict(row)
    # A paid plan needs a payment when it starts; without one the account moves to Free.
    change["pending_requires_payment"] = change["pending_plan"] in {"basic", "vip"} and not has_active_payment(
        conn, account_id, change["pending_plan"])
    return change


def _as_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _paid_period(conn, account_id: str, plan_code: str | None = None) -> dict | None:
    """The active off-store paid period (optionally of one plan) that ends in the future."""
    row = conn.execute(
        """SELECT plan_code, current_period_end FROM billing_subscriptions
           WHERE account_id=%s AND (%s::text IS NULL OR plan_code=%s) AND status='active'
             AND current_period_end IS NOT NULL AND current_period_end>NOW()
           ORDER BY current_period_end DESC LIMIT 1""",
        (account_id, plan_code, plan_code),
    ).fetchone()
    return {**row, "current_period_end": _as_datetime(row["current_period_end"])} if row else None


def entitlement_end(conn, account_id: str, subscription: dict):
    """When the current entitlement ends, or None when it has no stored end."""
    source = subscription.get("access_source")
    if source == "courtesy":
        return _as_datetime(subscription.get("expires_at"))
    if source == "self_service" and subscription.get("plan") in {"basic", "vip"}:
        return (_paid_period(conn, account_id, subscription["plan"]) or {}).get("current_period_end")
    return None


def _stop_renewal_above(conn, account_id: str, target: str) -> None:
    """A paid period of a plan above the target runs to its end and does not renew."""
    conn.execute(
        """UPDATE billing_subscriptions SET cancel_at_period_end=TRUE,updated_at=NOW()
           WHERE account_id=%s AND status='active' AND plan_code = ANY(%s::text[])
           RETURNING account_id""",
        (account_id, [code for code, rank in PLAN_RANK.items() if rank > PLAN_RANK[target]]),
    )


def store_managed(conn, account_id: str, subscription: dict) -> bool:
    """A self-service plan backed by an active store subscription."""
    if subscription.get("access_source") != "self_service" or not tables_exist(conn, ["store_subscriptions"]):
        return False
    return bool(conn.execute(
        "SELECT 1 FROM store_subscriptions WHERE account_id=%s AND status = ANY(%s::text[])",
        (account_id, list(STORE_ACTIVE_STATES)),
    ).fetchone())


def request_plan_change(conn, account_id: str, target: str) -> dict | None:
    """Schedule, undo or refuse a plan change; None means the caller applies it now.

    Locks the account's billing and subscription rows (always in that order), so
    concurrent or repeated requests for one account are serialized and the last
    one decides the pending change. The caller applies an immediate Free change
    in the same transaction; an upgrade goes through its activation path.
    """
    lock_billing_then_subscription(conn, account_id)
    row = conn.execute(
        """SELECT s.access_source, s.status, s.expires_at, p.code AS plan
           FROM account_subscriptions s JOIN plans p ON p.id=s.plan_id
           WHERE s.account_id=%s""",
        (account_id,),
    ).fetchone()
    if not row or row.get("access_source") == "owner":
        return None
    current = row["plan"]
    pending = pending_change(conn, account_id)
    if target == current:
        if not pending:
            return None
        clear_pending(conn, account_id)
        conn.execute(
            """UPDATE billing_subscriptions SET cancel_at_period_end=FALSE,updated_at=NOW()
               WHERE account_id=%s AND status='active' AND plan_code=%s
               RETURNING account_id""",
            (account_id, current),
        )
        return {"status": "plan_kept", "plan": current}
    if PLAN_RANK[target] > PLAN_RANK.get(current, 0):
        return None  # upgrade: immediate; the activation clears any pending change

    ends_at = entitlement_end(conn, account_id, row)
    if store_managed(conn, account_id, row):
        raise HTTPException(409, "Tu suscripción se administra desde App Store o Google Play. Cambiala o cancelala ahí; conservás tu plan hasta el final del período pagado.")
    if ends_at is None or ends_at <= datetime.now(timezone.utc):
        return None  # nothing left of the current period: the change applies now
    if not pending_supported(conn):
        # Never fall back to an immediate downgrade: the account would lose access it has.
        raise HTTPException(409, "El cambio de plan no está disponible en este momento. Tu plan actual sigue activo; intentá de nuevo más tarde.")

    plan = conn.execute("SELECT id FROM plans WHERE code=%s AND is_active=TRUE", (target,)).fetchone()
    if not plan:
        raise HTTPException(404, "Plan no disponible.")
    conn.execute(
        """UPDATE account_subscriptions
           SET pending_plan_id=%s,pending_effective_at=%s,pending_requested_at=NOW(),updated_at=NOW()
           WHERE account_id=%s
           RETURNING id""",
        (plan["id"], ends_at, account_id),
    )
    _stop_renewal_above(conn, account_id, target)
    return {"status": "downgrade_scheduled", "plan": current, "pending_plan": target,
            "effective_at": ends_at.isoformat()}


def plan_after_entitlement_end(conn, account_id: str, default_code: str) -> str:
    """The plan an account moves to when its current entitlement ends.

    ``default_code`` is what the caller would pick without a pending change (a
    still-paid plan, or Free). The caller then writes the returned plan. With a
    pending change:
    - a still-paid plan above the pending one keeps running until its own end,
      and the pending change moves to that date (access is never cut early);
    - otherwise the pending change is consumed: the account moves to the pending
      plan when it is Free or paid for, and to Free when it is not.
    """
    from backend.product_ops.service import has_active_payment

    pending = (pending_change(conn, account_id) or {}).get("pending_plan")
    if not pending:
        return default_code
    paid = _paid_period(conn, account_id, default_code) if default_code in {"basic", "vip"} else None
    if paid and PLAN_RANK[default_code] > PLAN_RANK[pending]:
        conn.execute(
            """UPDATE account_subscriptions SET pending_effective_at=%s,updated_at=NOW()
               WHERE account_id=%s RETURNING id""",
            (paid["current_period_end"], account_id),
        )
        _stop_renewal_above(conn, account_id, pending)
        return default_code
    clear_pending(conn, account_id)
    if pending == "free" or has_active_payment(conn, account_id, pending):
        return pending
    return "free"
