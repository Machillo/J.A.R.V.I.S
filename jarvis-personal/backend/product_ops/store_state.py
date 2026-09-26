"""Verified store purchases -> the account's plan.

Every function here receives a purchase state that store_apple / store_google
already verified with the store; nothing a client asserts reaches this module.

Rules:
- the product must be one of DINCR's (PRODUCTS); an unknown product grants nothing;
- sandbox purchases grant nothing unless DINCR_STORE_ACCEPT_SANDBOX=1 (never in
  production);
- a purchase is bound to one account forever: the account whose store customer
  token the purchase carries, or, for a purchase without one, the authenticated
  account that first presents it. Presenting it from another account is refused
  and recorded in store_purchase_conflicts (account ids only);
- states are absolute and ordered: an older state (earlier period end) never
  overwrites a newer one, except a revocation (refund), which always applies;
- the account's entitlement is the best live purchase across both stores (VIP over
  Basic, then the later end); with none live it falls back to Free. Owner and
  courtesy access are never touched.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from backend.product_ops.store_billing import PRODUCTS

LIVE = ("trialing", "active", "grace_period")
PLAN_RANK = {"vip": 2, "basic": 1}


def product_plan(product_id: str) -> tuple[str, str] | None:
    for plan, periods in PRODUCTS.items():
        for period, product in periods.items():
            if product["product_id"] == product_id:
                return plan, period
    return None


def customer_token(conn, account_id: str) -> str:
    """The token the app passes to the store (appAccountToken / obfuscatedExternalAccountId)."""
    row = conn.execute(
        """INSERT INTO store_customer_tokens(account_id) VALUES(%s)
           ON CONFLICT(account_id) DO UPDATE SET account_id=EXCLUDED.account_id
           RETURNING token::text AS token""",
        (account_id,),
    ).fetchone()
    return str(row["token"])


def _account_for_token(conn, token: str | None) -> str | None:
    if not token:
        return None
    row = conn.execute("SELECT account_id::text AS account_id FROM store_customer_tokens WHERE token::text=%s", (token,)).fetchone()
    return row["account_id"] if row else None


def _entitlement_end(purchase: dict[str, Any]) -> datetime | None:
    if purchase["status"] == "grace_period":
        return purchase.get("grace_ends_at") or purchase.get("current_period_end")
    if purchase["status"] == "trialing":
        return purchase.get("trial_ends_at") or purchase.get("current_period_end")
    return purchase.get("current_period_end")


def _as_time(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def record_verified_purchase(conn, state: dict[str, Any], *, claimed_account_id: str | None = None) -> dict[str, Any]:
    """Store a verified purchase state and recompute its account's plan.

    Returns {"account_id", "applied", "plan", "status", "conflict"?}. A purchase bound
    to another account comes back with conflict=True after recording it: the caller
    commits (so the record stays) and refuses the request. Raises HTTPException for
    an unknown product, a refused sandbox purchase or an unknown customer token.
    """
    mapped = product_plan(state["product_id"])
    if not mapped:
        raise HTTPException(422, "Producto de tienda desconocido.")
    if state["environment"] == "sandbox" and os.getenv("DINCR_STORE_ACCEPT_SANDBOX") != "1":
        raise HTTPException(409, "Las compras de prueba no activan planes.")
    plan_code, billing_period = mapped

    token_account = _account_for_token(conn, state.get("customer_token"))
    if state.get("customer_token") and not token_account:
        raise HTTPException(409, "La compra pertenece a otra cuenta.")
    bound = conn.execute(
        "SELECT account_id::text AS account_id, status, current_period_end FROM store_purchases WHERE provider=%s AND purchase_key=%s FOR UPDATE",
        (state["provider"], state["purchase_key"]),
    ).fetchone()
    account_id = (bound or {}).get("account_id") or token_account or claimed_account_id
    if not account_id:
        return {"account_id": None, "applied": False, "plan": None, "status": state["status"]}
    others = sorted({token_account, claimed_account_id} - {None, account_id})
    if others:
        for other in others:
            conn.execute(
                """INSERT INTO store_purchase_conflicts(provider,purchase_key,bound_account_id,claimed_account_id)
                   VALUES(%s,%s,%s,%s) RETURNING id""",
                (state["provider"], state["purchase_key"], account_id, other),
            )
        # Nothing else changes; the caller commits this record and refuses the request.
        return {"account_id": account_id, "applied": False, "plan": None, "status": state["status"], "conflict": True}

    newer = True
    if bound and state["status"] != "revoked":
        stored_end, incoming_end = _as_time(bound.get("current_period_end")), state.get("current_period_end")
        newer = bound["status"] != "revoked" and not (stored_end and incoming_end and incoming_end < stored_end)
    if newer:
        pending = product_plan(state["pending_product_id"]) if state.get("pending_product_id") else None
        conn.execute(
            """INSERT INTO store_purchases(
                   provider,purchase_key,account_id,environment,product_id,plan_code,billing_period,status,auto_renew,
                   trial_ends_at,current_period_end,grace_ends_at,revoked_at,pending_product_id,last_verified_at,updated_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
               ON CONFLICT(provider,purchase_key) DO UPDATE SET
                   environment=EXCLUDED.environment,product_id=EXCLUDED.product_id,plan_code=EXCLUDED.plan_code,
                   billing_period=EXCLUDED.billing_period,status=EXCLUDED.status,auto_renew=EXCLUDED.auto_renew,
                   trial_ends_at=EXCLUDED.trial_ends_at,current_period_end=EXCLUDED.current_period_end,
                   grace_ends_at=EXCLUDED.grace_ends_at,revoked_at=EXCLUDED.revoked_at,
                   pending_product_id=EXCLUDED.pending_product_id,last_verified_at=NOW(),updated_at=NOW()
               RETURNING purchase_key""",
            (state["provider"], state["purchase_key"], account_id, state["environment"], state["product_id"],
             plan_code, billing_period, state["status"], bool(state.get("auto_renew")), state.get("trial_ends_at"),
             state.get("current_period_end"), state.get("grace_ends_at"), state.get("revoked_at"),
             state.get("pending_product_id") if pending else None),
        )
        if state.get("superseded_key"):
            # An upgrade/downgrade on Google Play replaces the old purchase token.
            conn.execute(
                """UPDATE store_purchases SET status='superseded',superseded_by=%s,updated_at=NOW()
                   WHERE provider=%s AND purchase_key=%s AND account_id=%s AND status<>'revoked'
                   RETURNING purchase_key""",
                (state["purchase_key"], state["provider"], state["superseded_key"], account_id),
            )
    plan = recompute_account(conn, account_id)
    return {"account_id": account_id, "applied": newer, "plan": plan, "status": state["status"]}


def recompute_account(conn, account_id: str, *, now: datetime | None = None) -> str:
    """Derive store_subscriptions and the self-service plan from the account's verified purchases."""
    now = now or datetime.now(timezone.utc)
    purchases = [dict(row) for row in conn.execute(
        "SELECT * FROM store_purchases WHERE account_id=%s AND status<>'superseded'", (account_id,)).fetchall()]
    for purchase in purchases:
        for key in ("trial_ends_at", "current_period_end", "grace_ends_at", "updated_at"):
            purchase[key] = _as_time(purchase.get(key))
    live = [p for p in purchases if p["status"] in LIVE and (_entitlement_end(p) or now) > now]
    best = max(live, key=lambda p: (PLAN_RANK[p["plan_code"]], _entitlement_end(p))) if live else None
    shown = best or (max(purchases, key=lambda p: p["updated_at"] or now) if purchases else None)
    if shown:
        pending = product_plan(shown["pending_product_id"]) if shown.get("pending_product_id") else None
        status = shown["status"] if best else ("revoked" if shown["status"] == "revoked" else "expired")
        conn.execute(
            """INSERT INTO store_subscriptions(
                   account_id,provider,plan_code,billing_period,product_id,status,provider_subscription_id,
                   original_transaction_id,trial_ends_at,current_period_end,grace_ends_at,revoked_at,environment,
                   cancel_at_period_end,auto_renew,pending_plan_code,pending_billing_period,pending_product_id,
                   last_verified_at,created_at,updated_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW(),NOW())
               ON CONFLICT(account_id) DO UPDATE SET
                   provider=EXCLUDED.provider,plan_code=EXCLUDED.plan_code,billing_period=EXCLUDED.billing_period,
                   product_id=EXCLUDED.product_id,status=EXCLUDED.status,
                   provider_subscription_id=EXCLUDED.provider_subscription_id,
                   original_transaction_id=EXCLUDED.original_transaction_id,trial_ends_at=EXCLUDED.trial_ends_at,
                   current_period_end=EXCLUDED.current_period_end,grace_ends_at=EXCLUDED.grace_ends_at,
                   revoked_at=EXCLUDED.revoked_at,environment=EXCLUDED.environment,
                   cancel_at_period_end=EXCLUDED.cancel_at_period_end,auto_renew=EXCLUDED.auto_renew,
                   pending_plan_code=EXCLUDED.pending_plan_code,pending_billing_period=EXCLUDED.pending_billing_period,
                   pending_product_id=EXCLUDED.pending_product_id,last_verified_at=NOW(),updated_at=NOW()
               RETURNING account_id""",
            (account_id, shown["provider"], shown["plan_code"], shown["billing_period"], shown["product_id"], status,
             shown["purchase_key"] if shown["provider"] == "google" else None,
             shown["purchase_key"] if shown["provider"] == "apple" else None,
             shown.get("trial_ends_at"),
             # The entitlement end: the grace end while in grace (readers compare this column).
             _entitlement_end(shown) if best else shown.get("current_period_end"),
             shown.get("grace_ends_at"), shown.get("revoked_at"), shown["environment"],
             not shown["auto_renew"], shown["auto_renew"],
             pending[0] if pending else None, pending[1] if pending else None,
             shown.get("pending_product_id") if pending else None),
        )
    plan_code = best["plan_code"] if best else "free"
    protected = conn.execute(
        "SELECT access_source FROM account_subscriptions WHERE account_id=%s", (account_id,)).fetchone()
    if protected and protected.get("access_source") in {"owner", "courtesy"}:
        return plan_code  # managed independently of the stores
    plan = conn.execute("SELECT id FROM plans WHERE code=%s AND is_active=TRUE", (plan_code,)).fetchone()
    if not plan:
        raise HTTPException(503, "Plan DINCR no disponible.")
    conn.execute(
        """INSERT INTO account_subscriptions(account_id,plan_id,status,access_source,started_at,created_at,updated_at)
           VALUES(%s,%s,'active','self_service',NOW(),NOW(),NOW())
           ON CONFLICT(account_id) DO UPDATE SET plan_id=EXCLUDED.plan_id,status='active',
               access_source='self_service',updated_at=NOW()
           RETURNING account_id""",
        (account_id, plan["id"]),
    )
    return plan_code


def expire_lapsed(conn, *, now: datetime | None = None) -> int:
    """Recompute accounts whose derived entitlement ended without a store notification."""
    rows = conn.execute(
        """SELECT DISTINCT account_id::text AS account_id FROM store_subscriptions
           WHERE provider IN ('apple','google') AND status IN ('trialing','active','grace_period')
             AND current_period_end IS NOT NULL AND current_period_end <= COALESCE(%s, NOW())""",
        (now,),
    ).fetchall()
    for row in rows:
        recompute_account(conn, row["account_id"], now=now)
    return len(rows)
