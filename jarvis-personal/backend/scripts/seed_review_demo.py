"""Prepare the Google Play / App Store reviewer account with VIP access and sample data.

Usage (from jarvis-personal/, with the production DATABASE_URL loaded):

    python -m backend.scripts.seed_review_demo --email reviewer@example.com           # dry run
    python -m backend.scripts.seed_review_demo --email reviewer@example.com --apply

The reviewer account must sign in once (Google or Apple) and accept the legal
documents first, so its identity and workspace exist. The script then grants a
VIP courtesy and fills the account through the same service functions the app
uses, so every screen has realistic, fictitious data. It refuses to touch an
account that already has transactions, and never touches owner accounts.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

from backend.auth.current_user import reset_current_user, set_current_user
from backend.auth.saas import enrich_identity
from backend.auth.owner_role import owner_enabled
from backend.auth.service import get_allowed_user_by_email
from backend.auth.workspace_context import resolve_personal_workspace_context
from backend.core.database import get_connection
from backend.user_product import basic_service, service
from backend.user_product.models import (
    FinancialSituationRequest, GoalCreateRequest, RecurringItemRequest,
    SavingsPlanCreateRequest, TransactionCreateRequest, UserDebtCreateRequest,
)

COURTESY_DAYS = 365
COURTESY_NOTE = "Cuenta demo para revisión de Google Play / App Store"


def _identity(email: str) -> dict:
    user = get_allowed_user_by_email(email)
    if not user:
        raise SystemExit(f"No existe una cuenta para {email}. Iniciá sesión una vez en la app con esa cuenta.")
    if owner_enabled(email) or user.get("role") == "owner":
        raise SystemExit("La cuenta demo no puede ser una cuenta owner.")
    with get_connection() as conn:
        context = resolve_personal_workspace_context(conn, int(user["id"]))
        conn.rollback()
    return enrich_identity({**user, **context})


def _grant_vip(account_id: str) -> None:
    with get_connection() as conn:
        plan = conn.execute("SELECT id FROM plans WHERE code='vip' AND is_active=TRUE").fetchone()
        if not plan:
            raise SystemExit("El plan VIP no está activo en esta base de datos.")
        conn.execute(
            """INSERT INTO account_subscriptions(account_id,plan_id,status,access_source,started_at,expires_at,courtesy_note,granted_at,created_at,updated_at)
               VALUES(%s,%s,'active','courtesy',NOW(),NOW()+(%s*INTERVAL '1 day'),%s,NOW(),NOW(),NOW())
               ON CONFLICT(account_id) DO UPDATE SET plan_id=EXCLUDED.plan_id,status='active',access_source='courtesy',
                 started_at=NOW(),expires_at=EXCLUDED.expires_at,courtesy_note=EXCLUDED.courtesy_note,granted_at=NOW(),updated_at=NOW()""",
            (account_id, plan["id"], COURTESY_DAYS, COURTESY_NOTE),
        )
        conn.execute("UPDATE accounts SET plan_selected=TRUE,updated_at=NOW() WHERE id=%s", (account_id,))
        conn.commit()


def _sample_transactions(today: date) -> list[TransactionCreateRequest]:
    rows = []
    for months_back in (2, 1, 0):
        payday = (today.replace(day=1) - timedelta(days=31 * months_back)).replace(day=1)
        rows += [
            (payday, "Salario mensual", 850000, "income", "Salario"),
            (payday + timedelta(days=2), "Alquiler", 260000, "expense", "Vivienda"),
            (payday + timedelta(days=5), "Supermercado", 68500, "expense", "Comida"),
            (payday + timedelta(days=9), "Electricidad y agua", 32400, "expense", "Servicios"),
            (payday + timedelta(days=12), "Combustible", 30000, "expense", "Transporte"),
            (payday + timedelta(days=18), "Restaurante", 18900, "expense", "Entretenimiento"),
        ]
    return [
        TransactionCreateRequest(transaction_date=day, description=desc, amount=amount, transaction_type=kind, category=category)
        for day, desc, amount, kind, category in rows if day <= today
    ]


def _seed(today: date) -> dict[str, int]:
    service.update_financial_situation(FinancialSituationRequest(
        income_type="fixed", fixed_monthly_salary=850000, work_days_per_week=5, pay_frequency="monthly",
        essential_monthly_expenses=420000, liquid_savings=300000, emergency_fund_target=1200000,
        strategy_preference="balanced", discretionary_monthly_minimum=40000,
    ))
    transactions = _sample_transactions(today)
    for item in transactions:
        service.create_user_transaction(item)
    debts = [
        UserDebtCreateRequest(name="Tarjeta de crédito (demo)", total_amount=600000, remaining_amount=420000, monthly_payment=60000,
                              interest_rate=36, payment_day=15, debt_type="credit_card"),
        UserDebtCreateRequest(name="Préstamo personal (demo)", total_amount=2000000, remaining_amount=1350000, monthly_payment=95000,
                              interest_rate=18, payment_day=5, debt_type="loan", term_months=24),
    ]
    for debt in debts:
        service.create_user_debt(debt)
    service.create_user_goal(GoalCreateRequest(name="Viaje familiar", target_amount=900000, current_amount=150000,
                                               target_date=today + timedelta(days=270), priority="medium"))
    service.create_savings_plan(SavingsPlanCreateRequest(name="Ahorro mensual", monthly_amount=50000, saved_amount=100000,
                                                         start_date=today.replace(day=1), end_date=today + timedelta(days=365)))
    for recurring in (
        RecurringItemRequest(name="Internet hogar", amount=24900, category="Internet", due_day=10),
        RecurringItemRequest(name="Plataforma de streaming", amount=6500, category="Entretenimiento", due_day=20),
    ):
        basic_service.create_recurring_item(recurring)
    return {"transactions": len(transactions), "debts": len(debts), "goals": 1, "savings_plans": 1, "recurring": 2}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--apply", action="store_true", help="Write changes. Without it the script only validates.")
    args = parser.parse_args()

    identity = _identity(args.email.strip().lower())
    account_id = str(identity["account_id"])
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) AS total FROM transactions WHERE workspace_id=%s", (str(identity["workspace_id"]),),
        ).fetchone()
        conn.rollback()
    if int((existing or {}).get("total") or 0):
        raise SystemExit("La cuenta ya tiene movimientos. Usá una cuenta demo nueva para no mezclar datos.")

    if not args.apply:
        print(f"OK: {args.email} (cuenta {account_id}) está lista. Repetí con --apply para dar VIP y cargar datos demo.")
        return

    _grant_vip(account_id)
    # Re-enrich so the context reflects the VIP plan just granted.
    token = set_current_user(enrich_identity(identity))
    try:
        summary = _seed(date.today())
    finally:
        reset_current_user(token)
    print(f"Cuenta demo lista: VIP por {COURTESY_DAYS} días y datos de ejemplo {summary}.")


if __name__ == "__main__":
    main()
