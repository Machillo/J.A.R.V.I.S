from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any

from backend.ai.preferences import get_preference, set_preference
from backend.auth.current_user import get_current_account_id, get_current_user, get_current_workspace_id
from backend.core.database import get_connection
from backend.core.i18n import tx

PREFERENCE_KEY = "salvavidas"
DEFAULT_TARGET_MONTHS = 6
ALLOWED_TARGET_MONTHS = (1, 3, 6)

# The Owner boundary. The historical JARVIS Salvavidas (his Casa/Línea/Liberty
# obligations, the protected-expense picker over his fixed_expenses, the balance kept
# in a MultiMoney account) runs only for the server-resolved Owner role. DINCR Users
# (and admin) get the neutral model: months of their own real obligations.
OWNER_ROLE = "owner"


def _is_owner() -> bool:
    """Server-authoritative: the role resolved for this request, never a client flag."""
    return (get_current_user() or {}).get("role") == OWNER_ROLE


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _aliases(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except Exception:
            return [item.strip() for item in raw.split(",") if item.strip()]
    return []


def _monthly_amount(expected_amount: Any, frequency: str | None, interval_months: Any) -> float:
    amount = max(_f(expected_amount), 0.0)
    interval = max(int(_f(interval_months) or 1), 1)
    frequency = (frequency or "monthly").lower().strip()

    if frequency in {"annual", "yearly", "anual"}:
        return amount / 12.0
    if frequency in {"weekly", "semanal"}:
        return amount * 52.0 / 12.0
    if frequency in {"biweekly", "quincenal"}:
        return amount * 24.0 / 12.0
    return amount / interval


def _load_config() -> dict[str, Any]:
    raw = get_preference(PREFERENCE_KEY, {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    protected = raw.get("protected_expense_ids") or []
    candidate_target = int(_f(raw.get("target_months")) or DEFAULT_TARGET_MONTHS)
    return {
        "current_amount": max(_f(raw.get("current_amount")), 0.0),
        "protected_expense_ids": [int(item) for item in protected if str(item).isdigit()],
        "target_months": candidate_target if candidate_target in ALLOWED_TARGET_MONTHS else DEFAULT_TARGET_MONTHS,
    }


def _fetch_active_debts(workspace_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, debt_type, remaining_amount, monthly_payment, payment_day
            FROM debts
            WHERE workspace_id = %s
              AND COALESCE(remaining_amount, 0) > 0
            ORDER BY monthly_payment DESC, name ASC
            """,
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _fetch_fixed_expenses(workspace_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, category, expected_amount, currency, frequency,
                   interval_months, due_day, is_active, payment_method, aliases
            FROM fixed_expenses
            WHERE workspace_id = %s
              AND is_active = TRUE
              AND expected_amount IS NOT NULL
            ORDER BY due_day NULLS LAST, name ASC
            """,
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _looks_like_debt_duplicate(expense: dict[str, Any], debts: list[dict[str, Any]]) -> bool:
    """Hide fixed-expense mirrors of debts from the optional Salvavidas picker.

    Debts are authoritative in the debts table. Legacy fixed-expense rows such as
    Préstamo BAC, Préstamo Popular, Reloj/Tasa Cero and Minicuota must not be
    selectable again or the same monthly obligation would be counted twice.
    """
    name = _normalize(expense.get("name"))
    aliases = [_normalize(item) for item in _aliases(expense.get("aliases"))]
    haystack = " ".join([name, *aliases])

    explicit_debt_markers = (
        "prestamo",
        "minicuota",
        "mini cuota",
        "tasa cero",
        "deuda",
    )
    if any(marker in haystack for marker in explicit_debt_markers):
        return True

    for debt in debts:
        debt_name = _normalize(debt.get("name"))
        if not debt_name or not name:
            continue
        if debt_name == name or (len(name) >= 5 and name in debt_name) or (len(debt_name) >= 5 and debt_name in name):
            return True
        if any(alias and len(alias) >= 5 and (alias in debt_name or debt_name in alias) for alias in aliases):
            return True

    return False


def _is_mandatory_fixed_expense(expense: dict[str, Any]) -> bool:
    """V1 always-protected recurrent bills: house and phone line."""
    name = _normalize(expense.get("name"))
    category = _normalize(expense.get("category"))
    aliases = [_normalize(item) for item in _aliases(expense.get("aliases"))]
    haystack = " ".join([name, category, *aliases])

    house = name == "casa" or category == "vivienda" or "aporte casa" in haystack
    phone_line = (
        "linea" in name
        or "linea" in " ".join(aliases)
        or category in {"telefono", "telefonia"}
        or "liberty" in name
    )
    return house or phone_line


def _expense_payload(expense: dict[str, Any], monthly: float, *, selected: bool = False, mandatory: bool = False) -> dict[str, Any]:
    return {
        "id": expense.get("id"),
        "name": expense.get("name") or "Gasto",
        "category": expense.get("category") or "Gastos fijos",
        "expected_amount": round(max(_f(expense.get("expected_amount")), 0.0), 2),
        "monthly_amount": round(monthly, 2),
        "currency": expense.get("currency") or "CRC",
        "frequency": expense.get("frequency") or "monthly",
        "interval_months": int(_f(expense.get("interval_months")) or 1),
        "due_day": expense.get("due_day"),
        "selected": selected,
        "mandatory": mandatory,
    }


def get_salvavidas_state() -> dict[str, Any]:
    if _is_owner():
        return _owner_salvavidas_state()
    return _users_salvavidas_state()


def _owner_salvavidas_state() -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    config = _load_config()
    debts = _fetch_active_debts(workspace_id)
    fixed_expenses = _fetch_fixed_expenses(workspace_id)

    debt_items: list[dict[str, Any]] = []
    debt_monthly = 0.0
    for debt in debts:
        monthly = max(_f(debt.get("monthly_payment")), 0.0)
        debt_monthly += monthly
        debt_items.append({
            "id": debt.get("id"),
            "name": debt.get("name") or "Deuda",
            "debt_type": debt.get("debt_type") or "other",
            "monthly_payment": round(monthly, 2),
            "remaining_amount": round(max(_f(debt.get("remaining_amount")), 0.0), 2),
            "payment_day": debt.get("payment_day"),
        })

    mandatory_items: list[dict[str, Any]] = []
    optional_rows: list[tuple[dict[str, Any], float]] = []
    excluded_debt_duplicates: list[dict[str, Any]] = []
    mandatory_monthly = 0.0

    for expense in fixed_expenses:
        monthly = _monthly_amount(
            expense.get("expected_amount"),
            expense.get("frequency"),
            expense.get("interval_months"),
        )
        if _looks_like_debt_duplicate(expense, debts):
            excluded_debt_duplicates.append(_expense_payload(expense, monthly))
            continue
        if _is_mandatory_fixed_expense(expense):
            mandatory_monthly += monthly
            mandatory_items.append(_expense_payload(expense, monthly, selected=True, mandatory=True))
            continue
        optional_rows.append((expense, monthly))

    valid_optional_ids = {int(expense["id"]) for expense, _ in optional_rows}
    selected_ids = [item for item in config["protected_expense_ids"] if item in valid_optional_ids]
    selected_set = set(selected_ids)

    optional_items: list[dict[str, Any]] = []
    protected_monthly = 0.0
    for expense, monthly in optional_rows:
        selected = int(expense["id"]) in selected_set
        if selected:
            protected_monthly += monthly
        optional_items.append(_expense_payload(expense, monthly, selected=selected))

    monthly_base = debt_monthly + mandatory_monthly + protected_monthly
    target_months = config["target_months"]
    target = monthly_base * target_months
    linked_account = None
    with get_connection() as conn:
        table = conn.execute("SELECT to_regclass('public.account_balances') AS table_name").fetchone()
        if table and table.get("table_name"):
            linked_account = conn.execute(
                """SELECT id,current_balance,balance_as_of FROM account_balances
                   WHERE workspace_id=%s AND is_active=TRUE AND account_type='emergency_fund'
                   ORDER BY updated_at DESC,id DESC LIMIT 1""",
                (workspace_id,),
            ).fetchone()
    current = max(_f(linked_account.get("current_balance") if linked_account else config.get("current_amount")), 0.0)
    missing = max(target - current, 0.0)
    coverage = current / monthly_base if monthly_base > 0 else 0.0
    progress = min((current / target) * 100.0, 100.0) if target > 0 else 0.0

    milestones = []
    for months in (1, 3, 6):
        milestone_target = monthly_base * months
        milestones.append({
            "months": months,
            "target": round(milestone_target, 2),
            "reached": current >= milestone_target if milestone_target > 0 else False,
        })

    return {
        "status": "OK",
        "scope": "owner",
        "current_amount": round(current, 2),
        "monthly_base": round(monthly_base, 2),
        "target_months": target_months,
        "target_amount": round(target, 2),
        "missing_amount": round(missing, 2),
        "coverage_months": round(coverage, 2),
        "progress_percent": round(progress, 2),
        "protected_expense_ids": selected_ids,
        "components": {
            "debt_monthly_payments": round(debt_monthly, 2),
            "mandatory_fixed_expenses": round(mandatory_monthly, 2),
            "protected_expenses": round(protected_monthly, 2),
        },
        "debts": debt_items,
        "mandatory_expenses": mandatory_items,
        "available_expenses": optional_items,
        "excluded_debt_duplicates": excluded_debt_duplicates,
        "milestones": milestones,
        "verification": {
            "mode": "manual",
            "account_linked": bool(linked_account),
            "message": (
                tx("Saldo vinculado con la cuenta financiera real Salvavidas.",
                   "Balance linked to your real emergency fund account.")
                if linked_account else
                tx("Guardá el saldo para crear y vincular la cuenta financiera Salvavidas.",
                   "Save the balance to create and link your emergency fund account.")
            ),
        },
    }


def update_salvavidas(
    *,
    current_amount: float | None = None,
    protected_expense_ids: list[int] | None = None,
    target_months: int | None = None,
) -> dict[str, Any]:
    if not _is_owner():
        return _update_users_salvavidas(
            current_amount=current_amount, protected_expense_ids=protected_expense_ids, target_months=target_months,
        )
    config = _load_config()
    if current_amount is not None:
        config["current_amount"] = max(float(current_amount), 0.0)
    if protected_expense_ids is not None:
        clean_ids = []
        for item in protected_expense_ids:
            value = int(item)
            if value > 0 and value not in clean_ids:
                clean_ids.append(value)
        config["protected_expense_ids"] = clean_ids

    if target_months is not None:
        clean_target = int(target_months)
        if clean_target not in ALLOWED_TARGET_MONTHS:
            raise ValueError("El objetivo del Salvavidas debe ser de 1, 3 o 6 meses.")
        config["target_months"] = clean_target
    set_preference(PREFERENCE_KEY, config)
    if current_amount is not None:
        # Keep the old preference for compatibility while making Salvavidas a real account.
        from backend.finance.intelligence import upsert_account_balance
        upsert_account_balance(
            account_name="Salvavidas",
            current_balance=max(float(current_amount), 0.0),
            bank_name="MultiMoney",
            account_type="emergency_fund",
            currency="CRC",
            annual_interest_rate=0,
            include_in_net_worth=True,
            source="salvavidas",
            note="Saldo actualizado desde Strategy",
        )
    return get_salvavidas_state()


# DINCR Users ----------------------------------------------------------------------------

def _load_users_obligations(workspace_id: str, account_id: str) -> dict[str, Any]:
    """The workspace's real obligations and declared savings; no Owner table or name."""
    from backend.user_product.basic_service import _basic_tables_ready, _monthly_equivalent

    debts = _fetch_active_debts(workspace_id)
    with get_connection() as conn:
        recurring = [dict(row) for row in conn.execute(
            """SELECT id,name,amount,category,frequency,due_day FROM finva_recurring_items
               WHERE workspace_id=%s AND is_active=TRUE AND item_type='expense'
               ORDER BY due_day NULLS LAST,name""",
            (workspace_id,),
        ).fetchall()] if _basic_tables_ready(conn, "finva_recurring_items") else []
        profile = conn.execute(
            "SELECT liquid_savings FROM financial_profiles WHERE account_id=%s AND workspace_id=%s",
            (account_id, workspace_id),
        ).fetchone()
        # Before the neutral model, a Users Salvavidas save wrote the amount to the workspace's
        # own emergency_fund row (source 'salvavidas'). It is still the user's data: read it
        # when no savings are declared, so a saved amount never turns into "unknown".
        legacy = None
        table = conn.execute("SELECT to_regclass('public.account_balances') AS table_name").fetchone()
        if table and table.get("table_name"):
            legacy = conn.execute(
                """SELECT current_balance FROM account_balances
                   WHERE workspace_id=%s AND is_active=TRUE AND account_type='emergency_fund' AND source='salvavidas'
                   ORDER BY updated_at DESC,id DESC LIMIT 1""",
                (workspace_id,),
            ).fetchone()
    for row in recurring:
        row["monthly_amount"] = _monthly_equivalent(_f(row.get("amount")), row.get("frequency") or "monthly")
    savings = profile.get("liquid_savings") if profile else None
    legacy_balance = legacy.get("current_balance") if legacy else None
    if savings is not None:
        current, source = _f(savings), "declared"
    elif legacy_balance is not None:
        current, source = _f(legacy_balance), "previous_salvavidas_save"
    else:
        current, source = None, None
    return {"debts": debts, "recurring": recurring, "liquid_savings": current, "savings_source": source}


def _users_salvavidas_state() -> dict[str, Any]:
    """Neutral Salvavidas: 1/3/6 months of the workspace's real obligations.

    Obligations are the active debts' monthly payments plus the active recurring
    expense items. The fund is the savings the user declared in the financial
    situation; unknown savings stay unknown (never shown as zero coverage).
    """
    data = _load_users_obligations(get_current_workspace_id(), get_current_account_id())
    return _users_salvavidas_from(data, _load_config()["target_months"])


def _users_salvavidas_from(data: dict[str, Any], target_months: int) -> dict[str, Any]:
    debt_items = [{
        "id": debt.get("id"),
        "name": debt.get("name") or tx("Deuda", "Debt"),
        "debt_type": debt.get("debt_type") or "other",
        "monthly_payment": round(max(_f(debt.get("monthly_payment")), 0.0), 2),
        "remaining_amount": round(max(_f(debt.get("remaining_amount")), 0.0), 2),
        "payment_day": debt.get("payment_day"),
    } for debt in data.get("debts") or []]
    obligation_items = [{
        "id": row.get("id"),
        "name": row.get("name") or tx("Pago recurrente", "Recurring payment"),
        "category": row.get("category"),
        "expected_amount": round(max(_f(row.get("amount")), 0.0), 2),
        "monthly_amount": round(max(_f(row.get("monthly_amount")), 0.0), 2),
        "frequency": row.get("frequency") or "monthly",
        "due_day": row.get("due_day"),
    } for row in data.get("recurring") or []]
    debt_monthly = sum(item["monthly_payment"] for item in debt_items)
    recurring_monthly = sum(item["monthly_amount"] for item in obligation_items)
    monthly_base = round(debt_monthly + recurring_monthly, 2)
    target = round(monthly_base * target_months, 2)
    current = data.get("liquid_savings")
    known = current is not None
    status = "OK" if monthly_base > 0 else "needs_obligations"
    return {
        "status": status,
        "scope": "users",
        "current_amount": round(current, 2) if known else None,
        "current_amount_known": known,
        "current_amount_source": data.get("savings_source") if known else None,
        "monthly_base": monthly_base,
        "target_months": target_months,
        "allowed_target_months": list(ALLOWED_TARGET_MONTHS),
        "target_amount": target,
        "missing_amount": round(max(target - current, 0.0), 2) if known else None,
        "coverage_months": round(current / monthly_base, 2) if known and monthly_base > 0 else None,
        "progress_percent": round(min((current / target) * 100.0, 100.0), 2) if known and target > 0 else None,
        "components": {
            "debt_monthly_payments": round(debt_monthly, 2),
            "recurring_obligations": round(recurring_monthly, 2),
        },
        "debts": debt_items,
        "obligations": obligation_items,
        "milestones": [{
            "months": months,
            "target": round(monthly_base * months, 2),
            "reached": (current >= monthly_base * months) if known and monthly_base > 0 else False,
        } for months in ALLOWED_TARGET_MONTHS],
        "verification": {
            "mode": "declared",
            "message": (
                tx("El fondo es el ahorro que declaraste en tu situación financiera.",
                   "The fund is the savings you declared in your financial situation.")
                if known else
                tx("Declará tus ahorros en tu situación financiera para medir la cobertura.",
                   "Declare your savings in your financial situation to measure coverage.")
            ),
        },
    }


def _unchanged_savings(amount: float) -> bool:
    """Whether `amount` is just what the Users screen displayed (unknown shows as 0)."""
    data = _load_users_obligations(get_current_workspace_id(), get_current_account_id())
    shown = data.get("liquid_savings")
    return round(amount, 2) == round(shown if shown is not None else 0.0, 2)


def _update_users_salvavidas(
    *,
    current_amount: float | None,
    protected_expense_ids: list[int] | None,
    target_months: int | None,
) -> dict[str, Any]:
    """Users choose the 1/3/6-month goal and may update their declared savings.

    The fund is the declared liquid savings of the financial situation (one source of
    truth): a saved amount updates financial_profiles.liquid_savings, never an account
    named after a bank. Users have no protected-expense picker (every obligation
    counts); an empty list, which the historical screen always sends, changes nothing.
    """
    if protected_expense_ids:
        raise ValueError(tx(
            "En DINCR todas tus obligaciones cuentan para el Salvavidas.",
            "In DINCR every obligation counts toward your emergency fund.",
        ))
    clean_target = None
    if current_amount is not None and _unchanged_savings(float(current_amount)):
        # The historical web screen re-sends the amount it showed (0 for unknown) on every
        # save. Re-sending what is already shown is not an edit: never declare a zero.
        current_amount = None
    if target_months is not None:
        clean_target = int(target_months)
        if clean_target not in ALLOWED_TARGET_MONTHS:
            raise ValueError("El objetivo del Salvavidas debe ser de 1, 3 o 6 meses.")
    if current_amount is not None:
        amount = float(current_amount)
        if not math.isfinite(amount) or amount < 0 or amount > 999_999_999_999.99:
            raise ValueError(tx("Indicá un ahorro válido.", "Enter a valid savings amount."))
        with get_connection() as conn:
            updated = conn.execute(
                """UPDATE financial_profiles SET liquid_savings=%s,updated_at=NOW()
                   WHERE account_id=%s AND workspace_id=%s RETURNING account_id""",
                (round(amount, 2), get_current_account_id(), get_current_workspace_id()),
            ).fetchone()
            if not updated:
                raise ValueError(tx(
                    "Completá primero tu situación financiera para guardar tus ahorros.",
                    "Complete your financial situation first to save your savings.",
                ))
            conn.commit()
    if clean_target is not None:
        config = _load_config()
        config["target_months"] = clean_target
        set_preference(PREFERENCE_KEY, config)
    return get_salvavidas_state()
