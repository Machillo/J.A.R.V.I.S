"""Prove that a deleted account left nothing that points at the person (read-only).

Usage (from jarvis-personal/, DATABASE_URL pointing at the database to check),
with the ids recorded before deleting a test account:

    python -m backend.scripts.verify_account_deletion --account-id <uuid> --workspace-id <uuid> \
        [--workspace-id <uuid> ...] [--email-from-env VAR]

Exits 0 with "DELETION RESIDUE: NONE (public schema)" when no public table
references those identifiers, and 1 otherwise. Output is table, column and a
count only; identifiers are never printed. The email, if checked, is read from
the named environment variable so it never appears in shell history. The
transaction is READ ONLY and always rolled back. What is scanned, what is not
(auth schema, Vault, backups, third parties) and the deliberate retention are in
backend/auth/deletion_residue.py and are printed with the result.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

from backend.auth.deletion_residue import NOT_SCANNED, residue_report
from backend.core.database import get_connection


def _uuid(value: str) -> str:
    return str(uuid.UUID(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--account-id", required=True, type=_uuid)
    # Required: the account id is always nulled or cascaded, so without the workspace
    # ids the check could not see a row that kept only the workspace.
    parser.add_argument("--workspace-id", action="append", required=True, type=_uuid)
    parser.add_argument("--email-from-env", help="name of an environment variable holding the account email")
    args = parser.parse_args(argv)
    email = os.environ.get(args.email_from_env, "") if args.email_from_env else None
    with get_connection() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        still = conn.execute("SELECT count(*) AS n FROM accounts WHERE id=%s", (args.account_id,)).fetchone()
        residue = residue_report(conn, args.account_id, args.workspace_id, email=email)
        conn.rollback()
    if int(still["n"]):
        print("ACCOUNT STILL EXISTS: the deletion did not complete")
        return 1
    for item in residue:
        print(f"RESIDUE {item['table']}.{item['column']} rows={item['rows']}")
    print("DELETION RESIDUE: NONE (public schema)" if not residue else f"DELETION RESIDUE: {len(residue)} column(s)")
    print("Not scanned here: " + "; ".join(NOT_SCANNED))
    return 0 if not residue else 1


if __name__ == "__main__":
    sys.exit(main())
