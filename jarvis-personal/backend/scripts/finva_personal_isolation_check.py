"""
FINVA <-> PERSONAL runtime isolation check.

Creates temporary sentinel debt/goal rows inside the REAL Personal and Finva
workspaces, then attacks them through the application's real service layer from
the opposite authenticated context.

Existing financial rows are never targeted. Sentinels are deleted in finally.
No secrets or auth tokens are printed.
"""
from __future__ import annotations

import sys
import os
import uuid

from fastapi import HTTPException

from backend.auth.current_user import reset_current_user, set_current_user
from backend.core.database import get_connection
from backend.finance.service import (
    delete_debt,
    get_debts,
    update_debt,
)
from backend.goals.service import (
    delete_financial_goal,
    get_financial_goal,
    get_financial_goals,
    update_financial_goal,
)
from backend.user_product.service import (
    delete_user_debt,
    delete_user_goal,
    list_user_debts,
    list_user_goals,
    pay_user_debt,
)


PERSONAL_EMAIL = os.getenv("PERSONAL_ISOLATION_TEST_EMAIL", "")
FINVA_EMAIL = os.getenv("FINVA_ISOLATION_TEST_EMAIL", "")


def fail(message: str):
    raise AssertionError(message)


def resolve_context(email: str) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                a.id AS account_id,
                a.primary_email,
                a.role AS account_role,
                COALESCE(a.legacy_allowed_user_id, au.id) AS legacy_allowed_user_id,
                w.id AS workspace_id,
                w.name AS workspace_name,
                wm.member_role AS workspace_role
            FROM accounts a
            JOIN workspaces w
              ON w.owner_account_id = a.id
             AND w.workspace_type = 'personal'
             AND w.status = 'active'
            LEFT JOIN workspace_members wm
              ON wm.workspace_id = w.id
             AND wm.account_id = a.id
             AND wm.status = 'active'
            LEFT JOIN allowed_users au
              ON LOWER(au.email) = LOWER(a.primary_email)
            WHERE LOWER(a.primary_email) = LOWER(%s)
            ORDER BY w.created_at
            LIMIT 1
            """,
            (email,),
        ).fetchone()

    if not row:
        fail(f"No encontré account/workspace para {email}.")
    if row.get("legacy_allowed_user_id") is None:
        fail(f"No encontré allowed_users.id compatible para {email}.")

    return {
        "id": int(row["legacy_allowed_user_id"]),
        "email": row["primary_email"],
        "role": row.get("account_role") or "user",
        "status": "active",
        "account_id": str(row["account_id"]),
        "account_role": row.get("account_role") or "user",
        "workspace_id": str(row["workspace_id"]),
        "workspace_name": row["workspace_name"],
        "workspace_role": row.get("workspace_role") or "owner",
    }


def legacy_financial_user_id(email: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE LOWER(email)=LOWER(%s) ORDER BY id LIMIT 1",
            (email,),
        ).fetchone()
    if not row:
        fail(f"No encontré users.id financiero para {email}.")
    return int(row["id"])


def create_sentinels(ctx: dict, marker: str) -> dict:
    legacy_user_id = legacy_financial_user_id(ctx["email"])
    with get_connection() as conn:
        debt = conn.execute(
            """
            INSERT INTO debts(
                user_id,name,debt_type,total_amount,remaining_amount,monthly_payment,
                interest_rate,term_months,payment_day,created_at,first_payment_date,
                auto_update_monthly,installments_paid,updated_at,start_date,
                next_payment_date,last_payment_date,interest_method,fixed_fee_amount,
                workspace_id
            )
            VALUES(
                %s,%s,'other',987654.32,876543.21,12345.67,
                7.89,NULL,15,NOW(),NULL,FALSE,0,NOW(),NULL,
                NULL,NULL,'monthly',0,%s
            )
            RETURNING id,name,remaining_amount,workspace_id
            """,
            (legacy_user_id, f"ISOLATION_DEBT_{marker}", ctx["workspace_id"]),
        ).fetchone()

        goal = conn.execute(
            """
            INSERT INTO financial_goals(
                user_id,name,target_amount,current_amount,target_date,
                priority,status,created_at,workspace_id
            )
            VALUES(%s,%s,765432.10,12345.67,NULL,'medium','active',NOW(),%s)
            RETURNING id,name,current_amount,workspace_id
            """,
            (legacy_user_id, f"ISOLATION_GOAL_{marker}", ctx["workspace_id"]),
        ).fetchone()
        conn.commit()

    return {"debt": dict(debt), "goal": dict(goal)}


def use(ctx: dict):
    return set_current_user(ctx)


def blocked_http(callable_):
    try:
        callable_()
    except HTTPException as exc:
        return exc.status_code in (403, 404)
    return False


def main():
    personal = resolve_context(PERSONAL_EMAIL)
    finva = resolve_context(FINVA_EMAIL)

    if personal["account_id"] == finva["account_id"]:
        fail("Personal y Finva resolvieron al mismo account_id.")
    if personal["workspace_id"] == finva["workspace_id"]:
        fail("Personal y Finva resolvieron al mismo workspace_id.")

    marker = uuid.uuid4().hex[:10].upper()
    p = create_sentinels(personal, f"P_{marker}")
    f = create_sentinels(finva, f"F_{marker}")

    results: list[tuple[str, bool]] = []

    try:
        # ------------------------------------------------------------
        # FINVA -> PERSONAL using Finva's real user_product services.
        # ------------------------------------------------------------
        token = use(finva)
        try:
            debts = list_user_debts()
            goals = list_user_goals()
            results.append((
                "Finva list excludes Personal debt",
                not any(int(x["id"]) == int(p["debt"]["id"]) for x in debts),
            ))
            results.append((
                "Finva list excludes Personal goal",
                not any(int(x["id"]) == int(p["goal"]["id"]) for x in goals),
            ))
            results.append((
                "Finva payment against Personal debt blocked",
                blocked_http(lambda: pay_user_debt(int(p["debt"]["id"]), 1.0)),
            ))
            results.append((
                "Finva delete Personal debt blocked",
                blocked_http(lambda: delete_user_debt(int(p["debt"]["id"]))),
            ))
            results.append((
                "Finva delete Personal goal blocked",
                blocked_http(lambda: delete_user_goal(int(p["goal"]["id"]))),
            ))
        finally:
            reset_current_user(token)

        # ------------------------------------------------------------
        # PERSONAL -> FINVA using Personal's real services.
        # ------------------------------------------------------------
        token = use(personal)
        try:
            debts = get_debts()
            goals = get_financial_goals()
            results.append((
                "Personal list excludes Finva debt",
                not any(int(x["id"]) == int(f["debt"]["id"]) for x in debts),
            ))
            results.append((
                "Personal list excludes Finva goal",
                not any(int(x["id"]) == int(f["goal"]["id"]) for x in goals),
            ))

            debt_update = update_debt(
                int(f["debt"]["id"]),
                "ATTACKED_FROM_PERSONAL",
                "other",
                1.0,
                1.0,
                1.0,
                0.0,
                None,
                None,
            )
            results.append((
                "Personal update Finva debt blocked",
                debt_update.get("status") == "ERROR",
            ))
            results.append((
                "Personal delete Finva debt blocked",
                delete_debt(int(f["debt"]["id"])).get("status") == "ERROR",
            ))

            direct_goal = get_financial_goal(int(f["goal"]["id"]))
            results.append((
                "Personal direct read Finva goal blocked",
                direct_goal.get("status") == "ERROR",
            ))
            goal_update = update_financial_goal(
                int(f["goal"]["id"]),
                "ATTACKED_FROM_PERSONAL",
                1.0,
                1.0,
                None,
                "low",
                "active",
            )
            results.append((
                "Personal update Finva goal blocked",
                goal_update.get("status") == "ERROR",
            ))
            results.append((
                "Personal delete Finva goal blocked",
                delete_financial_goal(int(f["goal"]["id"])).get("status") == "ERROR",
            ))
        finally:
            reset_current_user(token)

        # ------------------------------------------------------------
        # Integrity: all four sentinel rows must still exist unchanged
        # in their original workspaces after every attack.
        # ------------------------------------------------------------
        with get_connection() as conn:
            debts_after = conn.execute(
                """
                SELECT id,name,remaining_amount,workspace_id
                FROM debts
                WHERE id IN (%s,%s)
                ORDER BY id
                """,
                (p["debt"]["id"], f["debt"]["id"]),
            ).fetchall()
            goals_after = conn.execute(
                """
                SELECT id,name,current_amount,workspace_id
                FROM financial_goals
                WHERE id IN (%s,%s)
                ORDER BY id
                """,
                (p["goal"]["id"], f["goal"]["id"]),
            ).fetchall()

        debt_expected = {
            int(p["debt"]["id"]): (
                p["debt"]["name"],
                float(p["debt"]["remaining_amount"]),
                personal["workspace_id"],
            ),
            int(f["debt"]["id"]): (
                f["debt"]["name"],
                float(f["debt"]["remaining_amount"]),
                finva["workspace_id"],
            ),
        }
        goal_expected = {
            int(p["goal"]["id"]): (
                p["goal"]["name"],
                float(p["goal"]["current_amount"]),
                personal["workspace_id"],
            ),
            int(f["goal"]["id"]): (
                f["goal"]["name"],
                float(f["goal"]["current_amount"]),
                finva["workspace_id"],
            ),
        }

        integrity = len(debts_after) == 2 and len(goals_after) == 2
        for row in debts_after:
            name, remaining, ws = debt_expected[int(row["id"])]
            integrity = (
                integrity
                and row["name"] == name
                and float(row["remaining_amount"]) == remaining
                and str(row["workspace_id"]) == ws
            )
        for row in goals_after:
            name, current, ws = goal_expected[int(row["id"])]
            integrity = (
                integrity
                and row["name"] == name
                and float(row["current_amount"]) == current
                and str(row["workspace_id"]) == ws
            )
        results.append(("Direct IDs cannot bypass workspace scope", integrity))

        print("\nFINVA <-> PERSONAL RUNTIME ISOLATION")
        print("=" * 52)
        print(f"Personal account : {personal['account_id']}")
        print(f"Personal workspace: {personal['workspace_id']}")
        print(f"Finva account    : {finva['account_id']}")
        print(f"Finva workspace  : {finva['workspace_id']}")
        print("-" * 52)

        for label, passed in results:
            print(f"{'PASS' if passed else 'FAIL'} | {label}")

        failed = [label for label, passed in results if not passed]
        if failed:
            print("\nRESULT: FAIL")
            for label in failed:
                print(f" - {label}")
            sys.exit(1)

        print("\nRESULT: PASS")
        print("Personal <-> Finva financial isolation is enforced by runtime workspace scope.")

    finally:
        # Cleanup ONLY rows created by this exact run.
        try:
            with get_connection() as conn:
                conn.execute(
                    "DELETE FROM debt_payments WHERE debt_id IN (%s,%s)",
                    (p["debt"]["id"], f["debt"]["id"]),
                )
                conn.execute(
                    "DELETE FROM debts WHERE id IN (%s,%s) AND name LIKE %s",
                    (p["debt"]["id"], f["debt"]["id"], f"ISOLATION_DEBT_%_{marker}"),
                )
                conn.execute(
                    "DELETE FROM financial_goals WHERE id IN (%s,%s) AND name LIKE %s",
                    (p["goal"]["id"], f["goal"]["id"], f"ISOLATION_GOAL_%_{marker}"),
                )
                conn.commit()
        except Exception as cleanup_exc:
            print(f"WARNING: cleanup needs review: {cleanup_exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
