"""The Owner's notices, read: what changed, where the money goes, what the automatic savings do.

The facts come from the stored notice. The meaning comes from his strategy and his locked savings
blocks as they are today, so it stays true when it is read later. Freed money is not new money: a
lower installment moves it from one debt to another, so no notice promises months saved from it;
it states the estimated date the strategy gives. Reading never writes. An unknown figure is left
out, never guessed.
"""
from __future__ import annotations

from typing import Any

from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection
from backend.core.i18n import tx
from backend.finance import owner_change_notices


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _crc(value: float) -> str:
    return "₡" + f"{value:,.0f}".replace(",", ".")


def savings_decision(blocks: dict[str, Any]) -> dict[str, Any]:
    """Whether the automatic savings take it, from the blocks engine's own answer."""
    status = blocks.get("status")
    proposal = blocks.get("proposal") or {}
    committed = _f(blocks.get("committed_weekly")) or 0.0
    already = tx(f" Ya apartás {_crc(committed)} por semana.", f" You already set aside {_crc(committed)} a week.") if committed > 0 else ""
    if status == "proposal":
        weekly = _crc(_f(proposal.get("weekly_amount")) or 0.0)
        name = (proposal.get("debt") or {}).get("name") or tx("tu próxima deuda larga", "your next long debt")
        months = proposal.get("term_months")
        if proposal.get("mode") == "presave":
            return {"decision": "partial", "weekly_amount": proposal.get("weekly_amount"), "text": tx(
                f"En parte: tus próximas deudas terminan pronto, así que el ataque sigue directo a ellas. Apartá solo {weekly} por semana para {name}.{already}",
                f"Partly: your next debts end soon, so the attack keeps going straight at them. Set aside only {weekly} a week for {name}.{already}")}
        return {"decision": "yes", "weekly_amount": proposal.get("weekly_amount"), "text": tx(
            f"Sí: apartá {weekly} más por semana para {name}, a {months} meses. Lo cambiás en tu banco; la app no puede hacerlo.{already}",
            f"Yes: set aside {weekly} more a week for {name}, for {months} months. You change it at your bank; the app can't.{already}")}
    reasons = {
        "short_debts_only": tx("tus deudas terminan pronto: es mejor abonarles directo.", "your debts end soon: it's better to pay them directly."),
        "pay_directly": tx("la plata quedaría trabada: la deuda terminaría antes de que venza el ahorro.", "the money would be stuck: the debt would end before the savings mature."),
        "no_surplus": tx("no alcanza el mínimo que acepta el banco, así que se va al ataque de deuda.", "it doesn't reach the bank's minimum, so it goes to the debt attack."),
        "no_debts": tx("no hay otra deuda para la que ahorrar.", "there is no other debt to save for."),
    }
    if status not in reasons:
        return {"decision": "unknown", "weekly_amount": None, "text": tx("No pude calcularlo ahora.", "I couldn't work it out right now.")}
    return {"decision": "no", "weekly_amount": None, "text": tx("De momento no: ", "Not for now: ") + reasons[status] + already}


def _changed(facts: dict[str, Any]) -> tuple[str, str, float | None]:
    """The notice's title, what changed, and the money freed each month (None: none or unknown)."""
    name = facts.get("debt_name") or tx("tu deuda", "your debt")
    old, new = _f(facts.get("old_payment")), _f(facts.get("new_payment"))
    if new is not None:
        if old is None:
            return tx(f"Nueva cuota de {name}", f"New installment for {name}"), tx(f"La cuota ahora es {_crc(new)}.", f"The installment is now {_crc(new)}."), None
        if new < old:
            freed = round(old - new, 2)
            return (tx(f"Bajó la cuota de {name}", f"The installment for {name} went down"),
                    tx(f"De {_crc(old)} a {_crc(new)}: te liberaste {_crc(freed)} al mes.", f"From {_crc(old)} to {_crc(new)}: that frees {_crc(freed)} a month."), freed)
        return tx(f"Cambió la cuota de {name}", f"The installment for {name} changed"), tx(f"De {_crc(old)} a {_crc(new)}.", f"From {_crc(old)} to {_crc(new)}."), None
    left = facts.get("new_installments")
    before = facts.get("old_installments")
    since = tx(f" (antes {before})", f" (before: {before})") if before else ""
    return (tx(f"Bajó el plazo de {name}", f"The term for {name} went down"),
            tx(f"Te quedan {left} cuotas{since}. La cuota sigue igual.", f"{left} installments left{since}. The installment stays the same."), None)


def _destination(blueprint: dict[str, Any], freed: float | None) -> str | None:
    if not freed:
        return None
    attack = next((item for item in blueprint.get("allocation_items") or [] if item.get("key") == "ataque_de_deuda"), None)
    target = (attack or {}).get("target_name")
    if target:
        return tx(f"A atacar {target}, según tu estrategia.", f"To pay down {target}, by your strategy.")
    return tx("Queda en tu sobrante y la estrategia lo reparte.", "It stays in your surplus and your strategy splits it.")


def get_owner_notices() -> dict[str, Any]:
    """GET: the notices with what they mean today (read-only)."""
    from backend.ai import strategy_dashboard
    from backend.ai.owner_debt_blocks import get_owner_debt_savings_blocks

    with get_connection() as conn:
        items = owner_change_notices.stored(conn, get_current_workspace_id())
    if not items:
        return {"items": [], "unread": 0}
    blueprint = strategy_dashboard._owner_strategy_blueprint()
    savings = savings_decision(get_owner_debt_savings_blocks())
    result = []
    for facts in items:
        title, changed, freed = _changed(facts)
        result.append({
            "id": facts.get("id"), "created_on": facts.get("created_on"), "read": bool(facts.get("read")), "debt_id": facts.get("debt_id"),
            "title": title, "changed": changed, "freed_monthly": freed, "destination": _destination(blueprint, freed),
            "savings": savings if freed else None, "debt_free_date": blueprint.get("estimated_debt_free_date"),
        })
    return {"items": result, "unread": sum(1 for item in result if not item["read"])}
