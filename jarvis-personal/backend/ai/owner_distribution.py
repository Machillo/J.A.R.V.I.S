"""Owner only: confirm that an exact-amount distribution was carried out, and record it.

The exact-amount distribution (``strategy_dashboard.get_owner_exact_distribution``) is a
planning answer: it writes nothing. CONFIRMAR is the Owner declaring that he followed it and
moved the money. Confirming records the confirmation and the real money each destination got,
with the mechanisms the app already uses for each one:

- ``ataque_de_deuda``: an extraordinary payment to principal (``record_extra_payment``), in the
  strategy's own debt order; a debt never receives more than it owes, the rest goes to the next
  debt in that order;
- ``fondo_de_emergencia``: a deposit into the Salvavidas (``deposit_to_owner_salvavidas``);
- ``meta_prioritaria``: a contribution to the goal the strategy funds (``apply_goal_contribution``);
- ``inversion`` / ``metas_o_inversion``: colones reserved to invest (an ``investment_cashflows``
  'reserve', as the Investment Center records it);
- ``vida_controlada``: money to live on. It is not a movement: spending is recorded when it
  happens, so nothing is written for it.

Consistency: the server recomputes the distribution and applies it only when it is exactly the
one the Owner reviewed: same destinations and amounts to the cent, adding up to the amount (the
part that goes by itself — the Salvavidas automatic contributions and the locked savings blocks'
contributions still to come in the cycle — counts as already placed: it is taken out of the
shares, not recorded here), and
the same plan (``fingerprint``: which debt gets how much, which goal). Otherwise nothing is written.
Everything is written in one transaction, committed once, under a per-workspace lock: a failure
leaves nothing applied. A confirmation key identifies one confirmation; repeating it (double
tap, retry) returns the confirmation already applied and writes nothing again.

What it does not know: which account the money came from. No other account balance is changed
(an unknown origin is never guessed).
"""
from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.core.i18n import tx
from backend.core.time import costa_rica_today
from backend.finance.debt_extra_payment import record_extra_payment
from backend.finance.debt_after_extra import mark_pending
from backend.finance.emergency_fund import SalvavidasDepositRefused, deposit_to_owner_salvavidas
from backend.goals.service import apply_goal_contribution

DEBT, EMERGENCY, GOAL, LIFE = "ataque_de_deuda", "fondo_de_emergencia", "meta_prioritaria", "vida_controlada"
INVESTMENT_KEYS = ("inversion", "metas_o_inversion")
SOURCE = "owner_distribution"


def _cents(value: Any) -> int:
    return int((Decimal(str(value or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _money(cents: int) -> float:
    return float(Decimal(cents) / 100)


def _items_in_cents(items: list[dict[str, Any]]) -> dict[str, int]:
    return {str(item.get("key")): _cents(item.get("amount")) for item in items if _cents(item.get("amount")) > 0}


def debt_attack_targets(debts: list[dict[str, Any]], amount: Any) -> tuple[list[dict[str, Any]], int]:
    """The debt part split in the strategy's own debt order (``_sort_debts_for_director``, Owner
    rules): each debt receives at most what it owes. Returns the targets and the cents no debt
    could take (more than all the debts owe)."""
    from backend.ai.strategy_dashboard import _sort_debts_for_director

    left = _cents(amount)
    targets = []
    # Sorted by id first: debts that tie on every strategy key get the same order in the preview
    # and in the confirmation, whatever order they were read in.
    active = sorted((debt for debt in debts if _cents(debt.get("remaining_amount")) > 0), key=lambda d: int(d.get("id") or 0))
    for debt in _sort_debts_for_director(active, owner_rules=True):
        if left <= 0:
            break
        take = min(left, _cents(debt.get("remaining_amount")))
        targets.append({"debt_id": debt.get("id"), "name": debt.get("name") or "Deuda", "amount": _money(take)})
        left -= take
    return targets, left


def confirmation_plan(strategy: dict[str, Any], debts: list[dict[str, Any]]) -> dict[str, Any]:
    """What CONFIRMAR would record for each destination of a computed distribution (shown before
    confirming), and whether it can be recorded at all."""
    goal = (strategy.get("goal_portfolio") or {}).get("active_goal") or {}
    steps, blocking = [], []
    for item in strategy.get("allocation_items") or []:
        key, amount = item.get("key"), item.get("amount")
        if key == DEBT:
            targets, left = debt_attack_targets(debts, amount)
            steps.append({"key": key, "amount": amount, "action": "debt_extra_payment", "targets": targets})
            if left > 0:
                blocking.append(tx("La parte para deudas es mayor que lo que se debe.", "The debt share is more than what is owed."))
        elif key == EMERGENCY:
            steps.append({"key": key, "amount": amount, "action": "salvavidas_deposit"})
        elif key == GOAL:
            steps.append({"key": key, "amount": amount, "action": "goal_contribution",
                          "goal_id": goal.get("id"), "goal_name": goal.get("name")})
            if not goal.get("id"):
                blocking.append(tx("No hay una meta activa para recibir su parte.", "There is no active goal to receive its share."))
        elif key in INVESTMENT_KEYS:
            steps.append({"key": key, "amount": amount, "action": "investment_reserve"})
        elif key == LIFE:
            steps.append({"key": key, "amount": amount, "action": "not_recorded"})
        else:
            steps.append({"key": key, "amount": amount, "action": "unsupported"})
            blocking.append(tx("Un destino de la estrategia no se puede registrar.", "A strategy destination cannot be recorded."))
    return {"steps": steps, "confirmable": not blocking, "blocking_reasons": blocking, "fingerprint": _fingerprint(steps)}


def _fingerprint(steps: list[dict[str, Any]]) -> str:
    """The plan the Owner reviewed, as one value: destination, action, cents, each debt's cents, goal."""
    canonical = [[step.get("key"), step.get("action"), _cents(step.get("amount")), step.get("goal_id"),
                  [[target.get("debt_id"), _cents(target.get("amount"))] for target in step.get("targets") or []]]
                 for step in steps]
    return hashlib.sha256(json.dumps(canonical, separators=(",", ":")).encode("utf-8")).hexdigest()


def _existing(conn, workspace_id: str, key: str) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT id, confirmation_key, amount, currency, items, applied, created_at
           FROM owner_distribution_confirmations WHERE workspace_id=%s AND confirmation_key=%s""",
        (workspace_id, key),
    ).fetchone()
    return dict(row) if row else None


def _replay(row: dict[str, Any], amount_cents: int) -> dict[str, Any]:
    if _cents(row.get("amount")) != amount_cents:
        raise HTTPException(status_code=409, detail=tx(
            "Esta confirmación ya se usó con otro monto.", "This confirmation was already used with another amount."))
    return {"status": "already_applied", "confirmation": row}


def _locked_debts(conn, workspace_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT id, name, debt_type, remaining_amount, monthly_payment, interest_rate
           FROM debts WHERE workspace_id=%s AND COALESCE(remaining_amount,0) > 0
           ORDER BY id FOR UPDATE""",
        (workspace_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _conflict(message_es: str, message_en: str) -> HTTPException:
    return HTTPException(status_code=409, detail=tx(message_es, message_en))


def confirm_owner_distribution(amount: Any, currency: str, confirmation_key: str,
                               expected_items: list[dict[str, Any]], plan_fingerprint: str) -> dict[str, Any]:
    """Record the distribution the Owner reviewed and declares carried out (see the module doc)."""
    from backend.ai.strategy_dashboard import _is_owner, get_owner_exact_distribution

    if not _is_owner():
        raise HTTPException(status_code=403, detail=tx("La distribución por monto exacto está disponible solo para el Owner.",
                                                       "Exact-amount distribution is available to the Owner only."))
    workspace_id = get_current_workspace_id()
    amount_cents = _cents(amount)
    with get_connection() as conn:
        # One confirmation at a time per workspace: the next one recomputes after this one commits.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{SOURCE}:{workspace_id}",))
        previous = _existing(conn, workspace_id, confirmation_key)
        if previous:
            return _replay(previous, amount_cents)

        distribution = get_owner_exact_distribution(amount, currency)
        strategy = distribution.get("strategy") or {}
        items = _items_in_cents(strategy.get("allocation_items") or [])
        if items != _items_in_cents(expected_items):
            raise _conflict("La distribución cambió desde que la revisaste. Revisala de nuevo antes de confirmar.",
                            "The distribution changed since you reviewed it. Review it again before confirming.")
        # What goes by itself in the cycle is out of the shares already (owner_commitments.absorb).
        by_itself = sum(_cents((strategy.get(key) or {}).get("taken_from_distribution"))
                        for key in ("automatic_savings", "debt_savings_blocks"))
        if sum(items.values()) + by_itself != amount_cents:
            raise _conflict("La distribución no suma exactamente el monto; no se registró nada.",
                            "The distribution does not add up to the amount exactly; nothing was recorded.")

        debts = _locked_debts(conn, workspace_id)
        plan = confirmation_plan(strategy, debts)
        if not plan["confirmable"]:
            raise HTTPException(status_code=409, detail=" ".join(plan["blocking_reasons"]))
        if plan["fingerprint"] != plan_fingerprint:
            # Same amounts, another plan: a debt balance or the goal changed since the review.
            raise _conflict("La distribución cambió desde que la revisaste. Revisala de nuevo antes de confirmar.",
                            "The distribution changed since you reviewed it. Review it again before confirming.")

        row = conn.execute(
            """INSERT INTO owner_distribution_confirmations (workspace_id, confirmation_key, amount, currency, items, confirmed_by)
               VALUES (%s, %s, %s, 'CRC', %s::jsonb, %s)
               RETURNING id, confirmation_key, amount, currency, items, created_at""",
            (workspace_id, confirmation_key, _money(amount_cents),
             json.dumps([{"key": key, "amount": _money(value)} for key, value in items.items()]), get_current_account_id()),
        ).fetchone()
        note = f"{SOURCE}:{row['id']}"
        today = costa_rica_today().isoformat()
        applied = []
        for step in plan["steps"]:
            if step["action"] == "debt_extra_payment":
                for target in step["targets"]:
                    payment = record_extra_payment(
                        conn, workspace_id, int(target["debt_id"]), target["amount"], payment_date=today,
                        description="Abono según distribución confirmada", source=SOURCE,
                        transaction_source=SOURCE, transaction_note=note,
                    )
                    if payment is None or _cents(payment["principal_amount"]) != _cents(target["amount"]):
                        raise _conflict("Una deuda cambió mientras se confirmaba; no se registró nada.",
                                        "A debt changed while confirming; nothing was recorded.")
                    # What the bank did with it (term or installment) is the Owner's to say later.
                    mark_pending(conn, workspace_id, int(target["debt_id"]), remind_on=None, source=SOURCE)
                    applied.append({"key": step["key"], "action": step["action"], "debt_id": target["debt_id"],
                                    "amount": target["amount"], "payment_id": payment["payment_id"],
                                    "new_remaining_amount": payment["new_remaining_amount"]})
            elif step["action"] == "salvavidas_deposit":
                try:
                    deposit = deposit_to_owner_salvavidas(conn, workspace_id, step["amount"], note=note)
                except SalvavidasDepositRefused as refused:
                    raise HTTPException(status_code=409, detail=str(refused)) from refused
                applied.append({"key": step["key"], "action": step["action"], "amount": step["amount"], **deposit})
            elif step["action"] == "goal_contribution":
                contribution = apply_goal_contribution(conn, workspace_id, int(step["goal_id"]), float(step["amount"]))
                if contribution is None:
                    raise _conflict("La meta ya no existe; no se registró nada.", "The goal no longer exists; nothing was recorded.")
                applied.append({"key": step["key"], "action": step["action"], "amount": step["amount"],
                                "goal_id": step["goal_id"], "new_amount": float(contribution["new_amount"])})
            elif step["action"] == "investment_reserve":
                reserve = conn.execute(
                    """INSERT INTO investment_cashflows (workspace_id, flow_date, flow_type, amount, currency, source, description)
                       VALUES (%s, %s, 'reserve', %s, 'CRC', %s, %s) RETURNING id""",
                    (workspace_id, today, step["amount"], SOURCE, note),
                ).fetchone()
                applied.append({"key": step["key"], "action": step["action"], "amount": step["amount"], "cashflow_id": reserve["id"]})
            else:
                applied.append({"key": step["key"], "action": step["action"], "amount": step["amount"]})

        conn.execute(
            "UPDATE owner_distribution_confirmations SET applied=%s::jsonb WHERE id=%s AND workspace_id=%s",
            (json.dumps(applied), row["id"], workspace_id),
        )
        conn.commit()
    return {"status": "applied", "confirmation": {**dict(row), "applied": applied}}
