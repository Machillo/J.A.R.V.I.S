"""Plan changes that respect the access the account already has.

DINCR sells Basic and VIP only through the App Store and Google Play. What an
account may use (account_subscriptions, the entitlement DINCR enforces) comes from:
- Owner: internal, never changed here;
- a courtesy (the launch promotion included): ``plan_id`` until ``expires_at``;
- a live store subscription (store_subscriptions): the store alone changes it,
  through verified store events;
- otherwise Free.

Rules:
- upgrade: immediate, through the existing activation paths; clears any pending change;
- downgrade or cancellation of a courtesy that still runs: scheduled for its
  ``expires_at`` (``pending_plan_id`` / ``pending_effective_at``), never immediate.
  Until then the current plan keeps every benefit;
- choosing the current plan again while a change is pending: keeps the plan (undo);
- an account with a live store subscription: any change is refused here and made
  in the store, which keeps the plan until the end of the paid period;
- when a courtesy ends, the account moves to the plan of its live store
  subscription, or to Free. A pending paid plan without a store subscription
  therefore becomes Free: DINCR never grants a paid plan nobody bought.

Nothing here assumes a trial or promotion length: every date is the stored one.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import HTTPException

from backend.core.schema_state import columns_exist, tables_exist

PLAN_RANK = {"free": 1, "basic": 2, "vip": 3}
PENDING_COLUMNS = ("pending_plan_id", "pending_effective_at", "pending_requested_at")
STORE_ENTITLED_STATES = ("trialing", "active", "grace_period")
# Only real stores; 'sandbox' rows come from the Owner-only QA simulator.
ENTITLING_STORES = ("apple", "google")
STORE_MANAGED_MESSAGE = ("Tu suscripción se administra desde App Store o Google Play. Cambiala o cancelala ahí; "
                         "conservás tu plan hasta el final del período pagado.")
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


def lock_subscription(conn, account_id: str) -> None:
    """Serialize every plan transition of one account on its subscription row."""
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


def store_plan(conn, account_id: str) -> str | None:
    """The plan of the account's live store subscription, if any.

    Live means trialing until ``trial_ends_at``, or active / in grace until
    ``current_period_end``, as the store last reported them.
    """
    if not tables_exist(conn, ["store_subscriptions"]):
        return None
    row = conn.execute(
        """SELECT plan_code FROM store_subscriptions
           WHERE account_id=%s AND provider = ANY(%s::text[]) AND status = ANY(%s::text[])
             AND COALESCE(CASE WHEN status='trialing' THEN trial_ends_at END, current_period_end, 'infinity'::timestamptz) > NOW()""",
        (account_id, list(ENTITLING_STORES), list(STORE_ENTITLED_STATES)),
    ).fetchone()
    return (row or {}).get("plan_code")


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
    change = dict(row)
    # A paid plan starts only with its store subscription; without one the account moves to Free.
    change["pending_requires_payment"] = (change["pending_plan"] in {"basic", "vip"}
                                          and store_plan(conn, account_id) != change["pending_plan"])
    return change


def _as_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def request_plan_change(conn, account_id: str, target: str) -> dict | None:
    """Schedule, undo or refuse a plan change; None means the caller applies it now.

    Locks the account's subscription row, so concurrent or repeated requests for
    one account are serialized and the last one decides the pending change. The
    caller applies an immediate Free change in the same transaction; an upgrade
    goes through its activation path.
    """
    lock_subscription(conn, account_id)
    row = conn.execute(
        """SELECT s.access_source, s.expires_at, p.code AS plan
           FROM account_subscriptions s JOIN plans p ON p.id=s.plan_id
           WHERE s.account_id=%s""",
        (account_id,),
    ).fetchone()
    if not row or row.get("access_source") == "owner":
        return None
    current = row["plan"]
    if target != current and store_plan(conn, account_id):
        raise HTTPException(409, STORE_MANAGED_MESSAGE)
    pending = pending_change(conn, account_id)
    if target == current:
        if not pending:
            return None
        clear_pending(conn, account_id)
        return {"status": "plan_kept", "plan": current}
    if PLAN_RANK[target] > PLAN_RANK.get(current, 0):
        return None  # upgrade: immediate; the activation clears any pending change

    ends_at = _as_datetime(row.get("expires_at")) if row.get("access_source") == "courtesy" else None
    if ends_at is None or ends_at <= datetime.now(timezone.utc):
        return None  # no running grant: the change applies now
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
    return {"status": "downgrade_scheduled", "plan": current, "pending_plan": target,
            "effective_at": ends_at.isoformat()}


def plan_after_entitlement_end(conn, account_id: str) -> str:
    """The plan an account moves to when its courtesy ends; consumes a pending change.

    The store is authoritative for paid plans: the account keeps the plan of its
    live store subscription, whatever was scheduled here, and otherwise moves to Free.
    """
    clear_pending(conn, account_id)
    return store_plan(conn, account_id) or "free"
