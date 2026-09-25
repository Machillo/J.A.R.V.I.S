"""Grant or revoke the internal Owner role explicitly (the only way to change it).

Usage (from jarvis-personal/, Python 3.11, DATABASE_URL of the environment; run
it only after the BACKUP_VERIFIED step of docs/security/migration-safety-protocol.md,
which this script does not check; the email is read from an environment variable
so it never appears in shell history or output):

    python3.11 -m backend.scripts.set_owner_role --email-from-env VAR --grant            # dry run
    python3.11 -m backend.scripts.set_owner_role --email-from-env VAR --grant --apply
    python3.11 -m backend.scripts.set_owner_role --email-from-env VAR --revoke --apply

Rules (backend/auth/owner_role.py):
- The account must exist (it signed in once) and be active.
- A grant requires the email to be in OWNER_EMAILS of the environment running the
  command (set it to the deployment's value): the role and the allowlist are two
  keys, and a grant the allowlist would refuse is a configuration mistake. The
  account must be active and bound to one Auth identity in both tables.
- The Owner subscription follows the role (grant: VIP 'owner'; revoke: Free).
- allowed_users.role and accounts.role change together, in one transaction,
  only if they still hold the expected previous role.
Output is a count and the result; no email, id or name is printed.
"""
from __future__ import annotations

import argparse
import os
import sys

from backend.auth.owner_role import OWNER_ROLE, owner_enabled


def change_role(conn, email: str, *, grant: bool) -> int:
    """Rows changed. Raises SystemExit on any refusal; the caller commits or rolls back.

    The role and the Owner subscription change together: a grant makes the plan VIP
    with access_source 'owner'; a revoke returns an 'owner' plan to Free self-service,
    so no Owner-sourced access outlives the role.
    """
    target, previous = (OWNER_ROLE, "user") if grant else ("user", OWNER_ROLE)
    if grant and not owner_enabled(email):
        raise SystemExit("REFUSED: the email is not in OWNER_EMAILS of the environment running this command.")
    legacy = conn.execute(
        """SELECT u.id,u.role,u.status,u.supabase_user_id,a.id AS account_id,a.supabase_user_id AS account_auth,
                  lower(trim(a.primary_email)) AS account_email
           FROM allowed_users u LEFT JOIN accounts a ON a.legacy_allowed_user_id=u.id
           WHERE lower(trim(u.email))=lower(trim(%s)) FOR UPDATE OF u""",
        (email,),
    ).fetchall()
    if len(legacy) != 1:
        raise SystemExit(f"REFUSED: expected exactly one account, found {len(legacy)}.")
    row = legacy[0]
    if grant:
        # Only a signed-in identity bound consistently in both tables can become Owner.
        if row["status"] != "active" or not row["account_id"] or not row["supabase_user_id"] \
                or str(row["supabase_user_id"]).lower() != str(row["account_auth"] or "").lower() \
                or row["account_email"] != email.strip().lower():
            raise SystemExit("REFUSED: the account is not active or not bound to one Auth identity in both tables.")
    if row["role"] == target:
        return 0
    if row["role"] != previous:
        raise SystemExit(f"REFUSED: unexpected current role '{row['role']}'.")
    changed = len(conn.execute(
        "UPDATE allowed_users SET role=%s WHERE id=%s AND role=%s RETURNING id", (target, row["id"], previous)).fetchall())
    changed += len(conn.execute(
        "UPDATE accounts SET role=%s,updated_at=NOW() WHERE legacy_allowed_user_id=%s AND role=%s RETURNING id",
        (target, row["id"], previous)).fetchall())
    if changed != (2 if row["account_id"] else 1):
        raise SystemExit("REFUSED: allowed_users and accounts disagree; nothing was changed.")
    if row["account_id"]:
        plan_code, source, only_from = ("vip", "owner", None) if grant else ("free", "self_service", "owner")
        changed += len(conn.execute(
            """UPDATE account_subscriptions s SET plan_id=p.id,status='active',access_source=%s,expires_at=NULL,
                      courtesy_note=NULL,granted_by=NULL,granted_at=NULL,updated_at=NOW()
               FROM plans p WHERE p.code=%s AND s.account_id=%s AND (%s::text IS NULL OR s.access_source=%s)
               RETURNING s.id""",
            (source, plan_code, row["account_id"], only_from, only_from)).fetchall())
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email-from-env", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--grant", action="store_true")
    action.add_argument("--revoke", action="store_true")
    parser.add_argument("--apply", action="store_true", help="commit the change (default: dry run)")
    args = parser.parse_args(argv)
    email = os.environ.get(args.email_from_env, "").strip()
    if not email:
        raise SystemExit(f"REFUSED: {args.email_from_env} is empty.")
    from backend.core.database import get_connection

    with get_connection() as conn:
        try:
            changed = change_role(conn, email, grant=args.grant)
        except SystemExit:
            conn.rollback()
            raise
        if args.apply:
            conn.commit()
            print(f"APPLIED: {changed} rows changed")
        else:
            conn.rollback()
            print(f"DRY RUN: {changed} rows would change (use --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
