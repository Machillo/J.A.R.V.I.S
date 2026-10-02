"""Who may put financial evidence into a workspace through mail.

Parsing and trust are separate. A parser recognizes any well-formed document; whether its
content may be stored depends only on WHO sent it. The From header is the one address of a
strict parse (a display name holding an address, a second address or trailing text is never
trusted), and payroll senders are trusted per workspace, by exact address, from that
workspace's own configuration (`payroll_trusted_senders`). No employer, person or address is
known in code; a lookalike domain or another workspace's trust never matches.
"""
from __future__ import annotations

import re


def single_sender_address(sender: str) -> str | None:
    """The one address of a From header, or None when the header is ambiguous or malformed."""
    header = (sender or "").strip()
    brackets = re.findall(r"<([^<>]*)>", header)
    if len(brackets) > 1:
        return None
    if brackets:
        display, _, trailing = header.partition("<")
        # A display name holding an address ("alerta@banco <x@evil>") or a second
        # recipient after the brackets is never a genuine notification.
        if "@" in display or trailing.split(">", 1)[-1].strip():
            return None
        address = brackets[0]
    else:
        address = header
    address = address.strip().lower()
    return address if re.fullmatch(r"[a-z0-9_.+\-]+@[a-z0-9.\-]+", address) else None


def trusted_payroll_sender(conn, workspace_id: str, sender: str) -> str | None:
    """The sender's address when this workspace trusts it for payroll receipts, else None."""
    address = single_sender_address(sender)
    if not address or not workspace_id:
        return None
    row = conn.execute(
        "SELECT 1 FROM payroll_trusted_senders WHERE workspace_id = %s AND sender_address = %s AND active",
        (workspace_id, address),
    ).fetchone()
    return address if row else None
