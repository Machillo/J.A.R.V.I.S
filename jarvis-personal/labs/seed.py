"""Write a synthetic dataset into the active Labs database (refuses anything else)."""
from __future__ import annotations

from typing import Any

from labs import db, synthetic

OWNED_BY_WORKSPACE = ("transactions", "salaries", "expenses", "debts", "financial_goals", "exchange_rates",
                      "account_balances")
OWNED_BY_ACCOUNT = ("finva_budget_items", "finva_recurring_items")


def _insert(cur, table: str, row: dict[str, Any]) -> None:
    columns = list(row)
    placeholders = ",".join(["%s"] * len(columns))
    cur.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})", [row[c] for c in columns])


def _identity(cur, user: synthetic.SyntheticUser) -> None:
    cur.execute("INSERT INTO allowed_users(id,email,role,status) VALUES(%s,%s,'user','active')",
                (user.allowed_id, user.email))
    cur.execute("INSERT INTO users(id,email,name,country,timezone) VALUES(%s,%s,%s,'Labs','UTC')",
                (user.users_id, user.email, user.display_name))
    cur.execute("""INSERT INTO accounts(id,legacy_allowed_user_id,primary_email,display_name,role,base_currency,labs_plan)
                   VALUES(%s,%s,%s,%s,'user',%s,%s)""",
                (user.account_id, user.allowed_id, user.email, user.display_name, user.base_currency, user.plan))
    cur.execute("INSERT INTO workspaces(id,workspace_key,owner_account_id,name) VALUES(%s,%s,%s,'Personal')",
                (user.workspace_id, f"personal:{user.account_id}", user.account_id))
    cur.execute("INSERT INTO workspace_members(workspace_id,account_id,member_role) VALUES(%s,%s,'owner')",
                (user.workspace_id, user.account_id))
    cur.execute("""INSERT INTO finva_gmail_connections(account_id,workspace_id,legacy_user_id,provider)
                   VALUES(%s,%s,%s,'labs-fixture')""", (user.account_id, user.workspace_id, user.users_id))


def write(dataset: synthetic.Dataset) -> dict[str, Any]:
    """Reset-independent: call ``db.reset`` first for a known state."""
    conn = db.connect_labs()
    try:
        with conn.cursor() as cur:
            for user in dataset.users:
                _identity(cur, user)
                for table, rows in user.rows.items():
                    for row in rows:
                        owner = {"workspace_id": user.workspace_id}
                        if table in OWNED_BY_ACCOUNT:
                            owner["account_id"] = user.account_id
                        _insert(cur, table, {**row, **owner})
        conn.commit()
        rejected, accepted = [], []
        if dataset.invalid_rows:
            user = dataset.users[0]
            with conn.cursor() as cur:
                for case in dataset.invalid_rows:
                    cur.execute("SAVEPOINT labs_invalid")
                    try:
                        _insert(cur, case["table"], {**case["row"], "workspace_id": user.workspace_id})
                        accepted.append(case["why"])
                    except Exception as exc:  # the database refused it, as intended
                        rejected.append({"why": case["why"], "sqlstate": getattr(exc, "pgcode", None)})
                    cur.execute("ROLLBACK TO SAVEPOINT labs_invalid")
            conn.rollback()
        return {"scenario": dataset.scenario, "seed": dataset.seed, "users": len(dataset.users),
                "rows": dataset.counts(), "invalid_rejected": rejected, "invalid_accepted": accepted}
    finally:
        conn.close()
