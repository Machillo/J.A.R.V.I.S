"""Daily financial history: the explicit job that records what reads no longer write (P0.2).

The health observation (`financial_health_snapshots`) and the Advisor Core strategy
(`advisor_current_strategy`, plus `advisor_strategy_history` when the strategy changes) used to
be written by GET requests. Reads are pure now; this job keeps both histories, and so their
future effects (deterioration history signals, strategy history), for every eligible workspace:

- VIP workspaces: the read-only equivalent of `require_feature("strategy_vip")`;
- the Owner workspace: the stored, allowlisted Owner identity (`is_verified_owner_account`).

Free and Basic never had this history (the lifecycle routes require `strategy_vip`; the
advisor and deterioration routes are internal), so they are not included.

The unit is one observation per workspace per Costa Rica calendar date; repeated or concurrent
runs of the same day are safe (see `persist_health_observation` and `_persist_strategy`).
Workspaces are discovered on the server; nothing is taken from the caller.
"""
from __future__ import annotations

import contextvars
import logging
from datetime import date
from typing import Any

from backend.advisor.core import _persist_strategy, compute_advisor_strategy
from backend.auth.current_user import reset_current_user, set_current_user
from backend.auth.owner_role import is_verified_owner_account
from backend.core.database import get_connection
from backend.core.i18n import DEFAULT_LANGUAGE, use_language
from backend.core.time import costa_rica_today
from backend.finance.deterioration import record_daily_health_snapshot

logger = logging.getLogger(__name__)

_CANDIDATES = """
    SELECT a.id::text AS account_id, w.id::text AS workspace_id, a.legacy_allowed_user_id AS legacy_user_id,
           a.role AS account_role, s.access_source, p.code AS plan_code,
           (p.code = 'vip' OR EXISTS (
               SELECT 1 FROM plan_features pf JOIN features f ON f.id = pf.feature_id
               WHERE pf.plan_id = s.plan_id AND pf.enabled = TRUE AND f.code = 'strategy_vip'
           )) AS strategy_vip
    FROM accounts a
    JOIN workspaces w ON w.owner_account_id = a.id AND w.workspace_type = 'personal'
                     AND w.workspace_key = 'personal:' || a.id::text AND w.status = 'active'
    LEFT JOIN account_subscriptions s ON s.account_id = a.id AND s.status = 'active'
          AND (s.access_source <> 'courtesy' OR (s.expires_at IS NOT NULL AND s.expires_at > NOW()))
    LEFT JOIN plans p ON p.id = s.plan_id
    WHERE a.status = 'active' AND a.legacy_allowed_user_id IS NOT NULL
      AND (a.role = 'owner' OR s.id IS NOT NULL)
    ORDER BY a.id
"""


def eligible_workspaces(conn) -> list[dict[str, Any]]:
    """The workspaces whose history the job keeps, with a server-built identity. Read-only."""
    from backend.product_ops.service import has_store_entitlement

    eligible = []
    for row in conn.execute(_CANDIDATES).fetchall() or []:
        row = dict(row)
        if row["account_role"] == "owner":
            # The stored Owner role counts only with the allowlist and the single-Owner rule;
            # otherwise the account is skipped (never processed as anyone else).
            if not is_verified_owner_account(conn, row["account_id"], row["workspace_id"]):
                continue
            role = "owner"
        else:
            if not row["strategy_vip"]:
                continue
            # Paid self-service plans count only with a live store subscription (require_feature).
            if row["access_source"] == "self_service" and row["plan_code"] in {"basic", "vip"} \
                    and not has_store_entitlement(conn, row["account_id"], row["plan_code"]):
                continue
            role = "admin" if row["account_role"] == "admin" else "user"
        eligible.append({
            "id": int(row["legacy_user_id"]),
            "account_id": row["account_id"],
            "workspace_id": row["workspace_id"],
            "role": role,
            "status": "active",
        })
    return eligible


def _record_workspace(identity: dict[str, Any], today: date) -> dict[str, Any]:
    """Health observation, then strategy, for one workspace, inside its own identity."""
    token = set_current_user(identity)
    try:
        with use_language(DEFAULT_LANGUAGE):
            health = record_daily_health_snapshot(today)
            persistence = _persist_strategy(compute_advisor_strategy())
    finally:
        reset_current_user(token)
    return {"health": health["health"], "strategy_changed": bool(persistence.get("changed")),
            "strategy_persisted": bool(persistence.get("persisted"))}


def run_daily_financial_history(today: date | None = None) -> dict[str, Any]:
    """Record the day's health observation and current strategy for every eligible workspace.

    Each workspace runs in a copied context with its own identity and its own transactions:
    a failure is counted and logged by error class only, and never touches another workspace.
    """
    day = today or costa_rica_today()
    with get_connection() as conn:
        workspaces = eligible_workspaces(conn)
    counts = {"eligible": len(workspaces), "recorded": 0, "strategy_changed": 0, "failed": 0}
    for identity in workspaces:
        try:
            result = contextvars.copy_context().run(_record_workspace, identity, day)
        except Exception as exc:  # isolate the workspace; no financial data in the log
            counts["failed"] += 1
            logger.warning("Daily financial history failed for one workspace error=%s", type(exc).__name__)
            continue
        counts["recorded"] += 1
        counts["strategy_changed"] += int(result["strategy_changed"])
    return {"status": "OK", "date": day.isoformat(), **counts}
