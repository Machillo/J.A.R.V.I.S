"""Upgrade live mailbox connections from an address identity to the provider's account id.

Usage (from jarvis-personal/, Python 3.11, DATABASE_URL and the Google/Microsoft
OAuth client settings of the environment being changed, after the migration
20260926110000_mailbox_single_owner.sql):

    python3.11 -m backend.scripts.backfill_mailbox_identity            # dry run (default)
    python3.11 -m backend.scripts.backfill_mailbox_identity --apply    # BACKUP_VERIFIED first

For each live connection still keyed by its address ('email:...'), it asks the
provider, with that connection's own token, for the account id: Google's ``sub``
(tokeninfo, only for DINCR's client) or Microsoft Graph's user ``id`` plus tenant.
Nothing else changes: no connection, message, token scope or account moves.

It aborts, writing nothing, when the result is ambiguous: two connections would
get the same identity, or an identity already belongs to another live connection.
A connection whose provider does not answer keeps its address identity (reported
as a count). The dry run writes nothing: it resolves Gmail connections only
(Google token refreshes do not rotate or store anything) and counts Outlook ones
as pending, because a Microsoft refresh may rotate the stored token. With --apply,
an Outlook connection whose token Microsoft rejects is marked
'reauthorization_required', exactly as a sync would. A connection with neither
provider scope is skipped: no token is ever sent to the other provider. Output is counts only; no address, account or token is printed.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from typing import Callable, Iterable


class Ambiguous(Exception):
    pass


def provider_of(row: dict) -> str | None:
    """The provider a connection's token belongs to, from its stored scope; never guessed."""
    scopes = row.get("granted_scopes") or []
    if "https://www.googleapis.com/auth/gmail.readonly" in scopes:
        return "gmail"
    if "Mail.Read" in scopes:
        return "microsoft"
    return None


def plan(rows: Iterable[dict], existing_keys: set[str], resolve: Callable[[dict], str | None]) -> tuple[dict[int, str], Counter]:
    """New key per connection id, or Ambiguous. ``existing_keys`` are the live keys not being replaced."""
    updates, counts = {}, Counter()
    for row in rows:
        key = resolve(row)
        if not key or key.startswith("email:"):
            counts["unresolved"] += 1
            continue
        updates[int(row["id"])] = key
        counts["resolved"] += 1
    repeated = [key for key, count in Counter(updates.values()).items() if count > 1]
    if repeated or set(updates.values()) & existing_keys:
        raise Ambiguous(f"{len(repeated)} identities shared by several connections; "
                        f"{len(set(updates.values()) & existing_keys)} already used by another live connection")
    return updates, counts


def _resolver(conn, *, apply: bool) -> Callable[[dict], str | None]:
    from backend.user_product import gmail_service, mail_oauth
    from backend.user_product import microsoft_mail as ms

    def resolve(row: dict) -> str | None:
        provider = provider_of(row)
        if provider is None or (provider == "microsoft" and not apply):
            return None
        try:
            refresh_token = gmail_service._vault_read(conn, str(row["refresh_token_secret_id"]))
            if provider == "gmail":
                client_id, client_secret, _ = gmail_service._google_config()
                response = gmail_service.requests.post("https://oauth2.googleapis.com/token", data={
                    "client_id": client_id, "client_secret": client_secret,
                    "refresh_token": refresh_token, "grant_type": "refresh_token"}, timeout=20)
                access = response.json().get("access_token") if response.status_code == 200 else None
                return mail_oauth.mailbox_key("gmail", row["google_email"], gmail_service._google_subject(access, client_id))
            access = ms._refresh(row, refresh_token)
            subject, tenant = ms._graph_identity(ms._graph_get(access, "/me"), access)
            return mail_oauth.mailbox_key("microsoft", row["google_email"], subject, tenant)
        except Exception:
            return None  # the provider did not answer: keep the address identity
    return resolve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the new identities (default: dry run)")
    args = parser.parse_args(argv)
    from backend.core.database import get_connection

    with get_connection() as conn:
        rows = [dict(row) for row in conn.execute(
            """SELECT id,account_id,google_email,granted_scopes,refresh_token_secret_id,mailbox_key
               FROM finva_gmail_connections WHERE status<>'disabled' AND mailbox_key LIKE 'email:%%' ORDER BY id""").fetchall()]
        existing = {row["mailbox_key"] for row in conn.execute(
            "SELECT mailbox_key FROM finva_gmail_connections WHERE status<>'disabled' AND mailbox_key NOT LIKE 'email:%%'").fetchall()}
        conn.commit()
    with get_connection() as conn:
        try:
            updates, counts = plan(rows, existing, _resolver(conn, apply=args.apply))
        except Ambiguous as ambiguous:
            print(f"ABORTED, nothing written: {ambiguous}")
            return 1
        print(f"candidates={len(rows)} resolved={counts['resolved']} unresolved={counts['unresolved']}")
        if not args.apply:
            print("DRY RUN: nothing written (use --apply)")
            return 0
        written = 0
        try:
            for connection_id, key in updates.items():
                written += len(conn.execute(
                    """UPDATE finva_gmail_connections SET mailbox_key=%s,updated_at=NOW()
                       WHERE id=%s AND status<>'disabled' AND mailbox_key LIKE 'email:%%' RETURNING id""",
                    (key, connection_id)).fetchall())
        except Exception as exc:  # e.g. a unique violation: its message would name the identity
            conn.rollback()
            print(f"ABORTED, rolled back: {type(exc).__name__}")
            return 1
        if written != len(updates):
            conn.rollback()
            print(f"ABORTED, rolled back: {written} of {len(updates)} rows still matched")
            return 1
        conn.commit()
        print(f"APPLIED: {written} connections now use the provider identity")
    return 0


if __name__ == "__main__":
    sys.exit(main())
