"""Canonical deterministic financial advisor.

Specialist finance modules calculate facts. Advisor Core is the only module
allowed to turn those facts into the current ordered strategy.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from backend.auth.current_user import get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.finance.deterioration import get_financial_deterioration
from backend.finance.emergency_fund import get_salvavidas_state
from backend.finance.intelligence import (
    calculate_goal_reserves,
    get_real_availability,
    list_account_balances,
    _fetch_active_goals,
)
from backend.finance.reconciliation import get_financial_reconciliation
from backend.finance.service import get_debts, get_financial_summary
from backend.finance.strategic_engine import calculate_debt_strategies, calculate_financial_health_score
from backend.finance.timeline import get_financial_timeline

ADVISOR_VERSION = "advisor-core-v2"


def _n(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _age_hours(value: Any, now: datetime | None = None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        return max((current - parsed.astimezone(timezone.utc)).total_seconds() / 3600, 0)
    except (TypeError, ValueError):
        return None


def _minimum_projected_balance(timeline: dict[str, Any]) -> float:
    balances = [_n(timeline.get("opening_available"))]
    balances.extend(_n(item.get("projected_balance")) for item in timeline.get("events") or [])
    return min(balances) if balances else 0.0


def _safe_usable_money(*, operating_surplus: float, liquidity: float, protected_minimum: float, timeline_floor: float) -> float:
    """Money usable now without consuming the protected month or future cash."""
    candidates = [
        max(_n(operating_surplus), 0.0),
        max(_n(liquidity) - _n(protected_minimum), 0.0),
        max(_n(timeline_floor) - _n(protected_minimum), 0.0),
    ]
    return round(min(candidates), 2)


def _ensure_strategy_tables(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS advisor_current_strategy (
            workspace_id UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
            advisor_version TEXT NOT NULL,
            strategy_hash TEXT NOT NULL,
            strategy JSONB NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS advisor_strategy_history (
            id BIGSERIAL PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
            advisor_version TEXT NOT NULL,
            strategy_hash TEXT NOT NULL,
            strategy JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def _persist_strategy(strategy: dict[str, Any]) -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    user_id = get_current_user_id()
    stable_strategy = {key: value for key, value in strategy.items() if key != "generated_at"}
    canonical = json.dumps(stable_strategy, ensure_ascii=False, sort_keys=True, default=str)
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with get_connection() as conn:
        _ensure_strategy_tables(conn)
        existing = conn.execute(
            "SELECT strategy_hash FROM advisor_current_strategy WHERE workspace_id=%s",
            (workspace_id,),
        ).fetchone()
        changed = not existing or existing.get("strategy_hash") != fingerprint
        if changed:
            conn.execute("""
                INSERT INTO advisor_strategy_history(
                    workspace_id,user_id,advisor_version,strategy_hash,strategy
                ) VALUES(%s,%s,%s,%s,%s::jsonb)
            """, (workspace_id, user_id, ADVISOR_VERSION, fingerprint, canonical))
        conn.execute("""
            INSERT INTO advisor_current_strategy(
                workspace_id,user_id,advisor_version,strategy_hash,strategy
            ) VALUES(%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT(workspace_id) DO UPDATE SET
                user_id=EXCLUDED.user_id,
                advisor_version=EXCLUDED.advisor_version,
                strategy_hash=EXCLUDED.strategy_hash,
                strategy=EXCLUDED.strategy,
                generated_at=NOW(),
                updated_at=NOW()
        """, (workspace_id, user_id, ADVISOR_VERSION, fingerprint, canonical))
        conn.commit()
    return {"strategy_hash": fingerprint, "changed": changed}


def _data_quality(summary: dict[str, Any], accounts: list[dict[str, Any]], debts: list[dict[str, Any]], reconciliation: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    if not (summary.get("setup") or {}).get("has_income_profile"):
        issues.append({"code": "income_missing", "severity": "blocking", "message": "Falta un ingreso mensual verificable."})
    liquid_accounts = [item for item in accounts if item.get("account_type") != "investment"]
    if not liquid_accounts:
        issues.append({"code": "accounts_missing", "severity": "blocking", "message": "No hay cuentas líquidas registradas."})
    stale_accounts = []
    for account in accounts:
        age = _age_hours(account.get("balance_as_of"))
        threshold = 36 if account.get("read_only") or account.get("source") in {"ibkr_flex", "ibkr_readonly"} else 24 * 7
        if age is None or age > threshold:
            stale_accounts.append(account.get("account_name") or "Cuenta")
    if stale_accounts:
        issues.append({"code": "stale_accounts", "severity": "warning", "message": "Saldos desactualizados: " + ", ".join(stale_accounts)})
    unknown_rates = [
        debt.get("name") or "Deuda"
        for debt in debts
        if _n(debt.get("remaining_amount")) > 0
        and _n(debt.get("interest_rate")) <= 0
        and str(debt.get("debt_type") or "").lower() not in {"tasa_cero", "family", "familiar"}
    ]
    if unknown_rates:
        issues.append({"code": "debt_rates_missing", "severity": "warning", "message": "Faltan tasas: " + ", ".join(unknown_rates)})
    rec_summary = reconciliation.get("summary") or {}
    if rec_summary.get("needs_review"):
        issues.append({"code": "reconciliation_pending", "severity": "warning", "message": f"{rec_summary['needs_review']} cuenta(s) requieren conciliación."})
    if rec_summary.get("unlinked"):
        issues.append({"code": "unlinked_transactions", "severity": "warning", "message": f"Hay {rec_summary['unlinked']} movimiento(s) sin cuenta."})
    blocking = sum(item["severity"] == "blocking" for item in issues)
    warnings = sum(item["severity"] == "warning" for item in issues)
    confidence = max(0.0, round(1 - blocking * 0.35 - warnings * 0.10, 2))
    return {
        "sufficient": blocking == 0,
        "fresh": not any(item["code"] == "stale_accounts" for item in issues),
        "confidence": confidence,
        "status": "reliable" if not issues else "blocked" if blocking else "review",
        "issues": issues,
    }


def build_advisor_strategy(*, persist: bool = True) -> dict[str, Any]:
    summary = get_financial_summary()
    accounts_report = list_account_balances()
    accounts = accounts_report.get("items") or []
    debts = [item for item in (get_debts() or []) if _n(item.get("remaining_amount")) > 0]
    reconciliation = get_financial_reconciliation()
    quality = _data_quality(summary, accounts, debts, reconciliation)
    timeline = get_financial_timeline(days=45)
    deterioration = get_financial_deterioration()
    salvavidas = get_salvavidas_state()
    availability = get_real_availability()
    debt_strategy = calculate_debt_strategies()
    goals = calculate_goal_reserves(_fetch_active_goals(get_current_workspace_id()))
    health = calculate_financial_health_score()

    liquidity = _n(timeline.get("opening_available"))
    timeline_floor = _minimum_projected_balance(timeline)
    first_negative = next((item for item in timeline.get("events") or [] if _n(item.get("projected_balance")) < 0), None)
    immediate_risk = {
        "exists": timeline_floor < 0 or deterioration.get("health") == "deteriorating",
        "minimum_projected_balance": round(timeline_floor, 2),
        "first_negative_event": first_negative,
        "deterioration_cause": deterioration.get("primary_cause"),
        "horizon_days": 45,
    }

    monthly_minimum = _n(salvavidas.get("monthly_base"))
    protected_current = _n(salvavidas.get("current_amount"))
    protection = {
        "monthly_minimum": round(monthly_minimum, 2),
        "current": round(protected_current, 2),
        "gap_one_month": round(max(monthly_minimum - protected_current, 0), 2),
        "coverage_months": round(_n(salvavidas.get("coverage_months")), 2),
        "target_months": 6,
    }

    target_debt = None
    if debt_strategy.get("status") == "OK" and debt_strategy.get("avalanche"):
        target_debt = debt_strategy["avalanche"].get("priority_debt")
        if target_debt:
            target_debt = {
                **target_debt,
                "why": f"Tiene la mayor tasa anual registrada ({_n(target_debt.get('interest_rate')):.2f}%) y atacarla primero minimiza intereses.",
            }

    usable = _safe_usable_money(
        operating_surplus=_n(availability.get("money_really_available")),
        liquidity=liquidity,
        protected_minimum=monthly_minimum,
        timeline_floor=timeline_floor,
    ) if quality["status"] == "reliable" else 0.0

    goal_items = []
    remaining_for_goals = usable
    for goal in goals.get("items") or []:
        required = _n(goal.get("monthly_required"))
        priority = str(goal.get("priority") or "").lower()
        urgent = priority in {"critical", "critica", "crítica"} and int(_n(goal.get("months_left")) or 99) <= 2
        blocked_by = None
        if protection["gap_one_month"] > 0 and not urgent:
            blocked_by = "Salvavidas menor a un mes"
        elif target_debt and _n(target_debt.get("interest_rate")) >= 10 and not urgent:
            blocked_by = "deuda prioritaria con tasa anual de 10% o más"
        fundable = 0.0 if blocked_by else min(required, remaining_for_goals)
        goal_items.append({**goal, "fundable_now": round(fundable, 2), "fully_fundable": fundable + 0.01 >= required, "blocked_by": blocked_by})
        remaining_for_goals = max(remaining_for_goals - fundable, 0)

    health_inputs = health.get("inputs") or {}
    debt_service_ratio = _n(health_inputs.get("debt_service_ratio"))
    highest_apr = _n(health_inputs.get("highest_debt_apr"))
    investment_blockers = []
    if quality["status"] != "reliable":
        investment_blockers.append("datos financieros insuficientes o sin verificar")
    if immediate_risk["exists"]:
        investment_blockers.append("riesgo de liquidez en los próximos 45 días")
    if protection["coverage_months"] < 3:
        investment_blockers.append("Salvavidas menor a tres meses")
    if highest_apr >= 10:
        investment_blockers.append("deuda con tasa anual de 10% o más")
    if debt_service_ratio > 0.25:
        investment_blockers.append("cuotas superiores al 25% del ingreso")
    investment = {
        "prudent": not investment_blockers,
        "recommended_amount": round(remaining_for_goals if not investment_blockers else 0, 2),
        "blockers": investment_blockers,
        "rule": "Invertir solo después de proteger liquidez, Salvavidas, deuda cara y metas financiables.",
    }

    actions: list[dict[str, Any]] = []
    if not quality["sufficient"]:
        issue = next(item for item in quality["issues"] if item["severity"] == "blocking")
        actions.append({"type": "complete_data", "title": issue["message"], "amount": 0, "why": "Sin este dato JARVIS no puede autorizar uso de dinero."})
    elif first_negative:
        actions.append({"type": "stabilize_cashflow", "title": f"Evitar saldo negativo antes de {first_negative.get('date')}", "amount": abs(round(_n(first_negative.get("projected_balance")), 2)), "why": first_negative.get("name")})
    elif (deterioration.get("primary_cause") or {}).get("severity") == "high" and (deterioration.get("primary_cause") or {}).get("code") != "salvavidas":
        cause = deterioration["primary_cause"]
        actions.append({"type": "mitigate_deterioration", "title": cause.get("title"), "amount": 0, "why": cause.get("context")})
    reconciliation_summary = reconciliation.get("summary") or {}
    if reconciliation_summary.get("needs_review") or reconciliation_summary.get("unlinked"):
        actions.append({"type": "reconcile", "title": "Completar conciliación financiera", "amount": 0, "why": "Los saldos reales deben confirmarse antes de mover excedentes."})
    if protection["gap_one_month"] > 0:
        actions.append({"type": "emergency_fund", "title": "Completar un mes de Salvavidas", "amount": min(protection["gap_one_month"], max(usable, 0)), "why": "Es el mínimo protegido antes de acelerar deuda o invertir."})
    if target_debt:
        debt_amount = usable if protection["gap_one_month"] <= 0 else 0.0
        debt_reason = target_debt.get("why")
        if protection["gap_one_month"] > 0:
            debt_reason += " Queda en espera hasta completar el primer mes de Salvavidas."
        actions.append({"type": "debt", "title": f"Abonar a {target_debt.get('name')}", "amount": round(debt_amount, 2), "why": debt_reason})
    if not actions and goal_items:
        goal = goal_items[0]
        actions.append({"type": "goal", "title": f"Financiar {goal.get('name')}", "amount": goal.get("fundable_now"), "why": "Es la meta activa de mayor prioridad y fecha."})
    if not actions and investment["prudent"]:
        actions.append({"type": "investment", "title": "Invertir el excedente autorizado", "amount": investment["recommended_amount"], "why": "No quedan bloqueos financieros previos."})
    if not actions:
        actions.append({"type": "hold", "title": "No mover dinero adicional hoy", "amount": 0, "why": "No existe excedente seguro después de obligaciones y protección."})

    strategy = {
        "advisor_version": ADVISOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_quality": quality,
        "immediate_risk": immediate_risk,
        "minimum_protection": protection,
        "debt_target": target_debt,
        "usable_money": {
            "amount": usable,
            "operating_surplus": round(_n(availability.get("money_really_available")), 2),
            "liquidity": round(liquidity, 2),
            "timeline_floor": round(timeline_floor, 2),
            "formula": "mínimo entre excedente operativo, liquidez sobre protección y piso proyectado sobre protección",
        },
        "fundable_goals": goal_items,
        "investment": investment,
        "next_action": actions[0],
        "action_plan": actions[:3],
        "health": health,
        "financial_score": health.get("score"),
        "health_label": health.get("level"),
        "confidence": quality.get("confidence"),
        "primary_diagnosis": deterioration.get("primary_cause"),
        "forecast": {
            "opening_available": timeline.get("opening_available"),
            "ending_available": timeline.get("ending_available"),
            "minimum_projected_balance": round(timeline_floor, 2),
            "horizon_days": 45,
        },
        "summary": {
            "available_cash": usable,
            "net_worth": (deterioration.get("context") or {}).get("net_worth"),
            "debt_total": round(sum(_n(item.get("remaining_amount")) for item in debts), 2),
            "monthly_debt_payments": round(sum(_n(item.get("monthly_payment")) for item in debts), 2),
            "debt_payment_ratio": health_inputs.get("debt_service_ratio"),
            "main_goal": goal_items[0] if goal_items else None,
        },
        "decision_policy": "datos > riesgo 45 días > conciliación > 1 mes Salvavidas > deuda cara > metas > 3-6 meses Salvavidas > inversión",
        "priorities": [item["title"] for item in actions[:3]],
        "advice": [actions[0].get("why") or ""],
        "warnings": [item["message"] for item in quality.get("issues") or []],
    }
    persistence = _persist_strategy(strategy) if persist else {"changed": False, "strategy_hash": None}
    return {**strategy, "persistence": persistence}


def get_strategy_history(limit: int = 20) -> list[dict[str, Any]]:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        _ensure_strategy_tables(conn)
        rows = conn.execute("""
            SELECT id,advisor_version,strategy_hash,strategy,created_at
            FROM advisor_strategy_history WHERE workspace_id=%s
            ORDER BY created_at DESC,id DESC LIMIT %s
        """, (workspace_id, max(1, min(int(limit or 20), 100)))).fetchall()
        conn.commit()
    return [dict(row) for row in rows]
