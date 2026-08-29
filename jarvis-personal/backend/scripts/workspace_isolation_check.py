"""
4E.1 controlled isolation check.

Runs against the configured JARVIS Personal database, creates a temporary sibling
workspace under the owner account, inserts sentinel transactions through the real
transaction service, attacks them from the opposite workspace, and cleans up.

No secrets are printed. No existing financial row is modified.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date

from backend.auth.current_user import reset_current_user, set_current_user
from backend.core.database import get_connection
from backend.transactions.service import (
    create_transaction,
    delete_transaction,
    get_transaction,
    get_transactions,
    update_transaction,
)


def fail(message: str):
    raise AssertionError(message)


def owner_contexts():
    owner_email = next(
        (email.strip().lower() for email in os.getenv("OWNER_EMAILS", "").split(",") if email.strip()),
        None,
    )

    with get_connection() as conn:
        if owner_email:
            row = conn.execute(
                """
                SELECT au.id AS legacy_user_id, au.email, a.id AS account_id,
                       w.id AS workspace_id, w.name AS workspace_name
                FROM allowed_users au
                JOIN accounts a ON a.legacy_allowed_user_id=au.id
                JOIN workspaces w ON w.owner_account_id=a.id
                                 AND w.workspace_type='personal'
                WHERE LOWER(au.email)=%s
                LIMIT 1
                """,
                (owner_email,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT au.id AS legacy_user_id, au.email, a.id AS account_id,
                       w.id AS workspace_id, w.name AS workspace_name
                FROM allowed_users au
                JOIN accounts a ON a.legacy_allowed_user_id=au.id
                JOIN workspaces w ON w.owner_account_id=a.id
                                 AND w.workspace_type='personal'
                WHERE au.role='owner'
                ORDER BY au.id
                LIMIT 1
                """
            ).fetchone()

        if not row:
            fail("No encontré owner + account + workspace Personal.")

        workspace_b = str(uuid.uuid4())
        key = f"isolation-test:{uuid.uuid4()}"
        conn.execute(
            """
            INSERT INTO workspaces(id, workspace_key, owner_account_id, name, workspace_type, status)
            VALUES (%s,%s,%s,'4E Isolation Temporary','business','active')
            """,
            (workspace_b, key, row["account_id"]),
        )
        conn.execute(
            """
            INSERT INTO workspace_members(workspace_id, account_id, member_role, status)
            VALUES (%s,%s,'owner','active')
            """,
            (workspace_b, row["account_id"]),
        )
        conn.commit()

    base = {
        "id": int(row["legacy_user_id"]),
        "email": row["email"],
        "role": "owner",
        "status": "active",
        "account_id": str(row["account_id"]),
        "account_role": "owner",
        "workspace_role": "owner",
    }
    a = {**base, "workspace_id": str(row["workspace_id"]), "workspace_name": row["workspace_name"]}
    b = {**base, "workspace_id": workspace_b, "workspace_name": "4E Isolation Temporary"}
    return a, b


def use(ctx):
    return set_current_user(ctx)


def main():
    a, b = owner_contexts()
    created_ids = []

    try:
        today = date.today().isoformat()

        token = use(a)
        try:
            tx_a = create_transaction(today, "4E_SENTINEL_A", 111.0, "income", "Otros ingresos", source="isolation_test")
            created_ids.append(tx_a["id"])
        finally:
            reset_current_user(token)

        token = use(b)
        try:
            tx_b = create_transaction(today, "4E_SENTINEL_B", 222.0, "income", "Otros ingresos", source="isolation_test")
            created_ids.append(tx_b["id"])
        finally:
            reset_current_user(token)

        results = []

        token = use(a)
        try:
            rows_a = get_transactions()
            results.append(("A can read A data", any(r["id"] == tx_a["id"] for r in rows_a)))
            results.append(("A list excludes B", not any(r["id"] == tx_b["id"] for r in rows_a)))
            results.append(("A direct read B blocked", get_transaction(tx_b["id"]).get("status") == "ERROR"))

            blocked_update = update_transaction(
                tx_b["id"], today, "ATTACKED_FROM_A", 999.0,
                "income", "Otros ingresos", source="isolation_test"
            )
            results.append(("A update B blocked", blocked_update.get("status") == "ERROR"))
            results.append(("A delete B blocked", delete_transaction(tx_b["id"]).get("status") == "ERROR"))
        finally:
            reset_current_user(token)

        token = use(b)
        try:
            rows_b = get_transactions()
            results.append(("B can read B data", any(r["id"] == tx_b["id"] for r in rows_b)))
            results.append(("B list excludes A", not any(r["id"] == tx_a["id"] for r in rows_b)))
            results.append(("B direct read A blocked", get_transaction(tx_a["id"]).get("status") == "ERROR"))

            blocked_update = update_transaction(
                tx_a["id"], today, "ATTACKED_FROM_B", 999.0,
                "income", "Otros ingresos", source="isolation_test"
            )
            results.append(("B update A blocked", blocked_update.get("status") == "ERROR"))
            results.append(("B delete A blocked", delete_transaction(tx_a["id"]).get("status") == "ERROR"))
        finally:
            reset_current_user(token)

        # Confirm attacks did not mutate sentinels.
        with get_connection() as conn:
            persisted = conn.execute(
                """
                SELECT id, workspace_id, description, amount
                FROM transactions
                WHERE id IN (%s,%s)
                ORDER BY id
                """,
                (tx_a["id"], tx_b["id"]),
            ).fetchall()
        expected = {
            tx_a["id"]: (a["workspace_id"], "4E_SENTINEL_A", 111.0),
            tx_b["id"]: (b["workspace_id"], "4E_SENTINEL_B", 222.0),
        }
        integrity = len(persisted) == 2
        for row in persisted:
            ws, desc, amount = expected[row["id"]]
            integrity = integrity and str(row["workspace_id"]) == ws and row["description"] == desc and float(row["amount"]) == amount
        results.append(("Direct IDs cannot bypass scope", integrity))

        print("\nJARVIS 4E.1 WORKSPACE ISOLATION")
        print("=" * 44)
        for label, passed in results:
            print(f"{'PASS' if passed else 'FAIL'} | {label}")

        failed = [label for label, passed in results if not passed]
        if failed:
            print("\nRESULT: FAIL")
            for item in failed:
                print(f" - {item}")
            sys.exit(1)

        print("\nRESULT: PASS")
        print("A ↔ B transaction isolation is enforced by the runtime service.")
    finally:
        # Cleanup by exact sentinel IDs + temporary workspace. Never touches existing data.
        try:
            with get_connection() as conn:
                if created_ids:
                    conn.execute(
                        "DELETE FROM transactions WHERE id = ANY(%s) AND source='isolation_test'",
                        (created_ids,),
                    )
                conn.execute(
                    "DELETE FROM workspaces WHERE id=%s AND name='4E Isolation Temporary'",
                    (b["workspace_id"],),
                )
                conn.commit()
        except Exception as cleanup_exc:
            print(f"WARNING: cleanup needs review: {cleanup_exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
