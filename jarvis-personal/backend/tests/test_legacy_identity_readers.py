"""Inventory of the runtime code that still resolves identity through the legacy ids.

The canonical identity is Supabase user -> accounts -> workspaces; financial rows are
owned by workspace_id. The legacy ids (allowed_users.id, users.id, and the user_id
column that holds either) are being retired. This test is a ratchet: a new reader
that joins or looks up through a legacy id fails here, and removing one requires
lowering its count below, so the inventory always matches the code.

Every remaining entry has an owner phase:
- Owner identity (email monitor, IBKR, sports digest, system push, login role):
  resolved canonically once the explicit Owner role (owner_role) is on main.
- The auth bridge (login binding, account deletion, legacy users rows for old
  finance foreign keys): retired together with the user_id writers.
- Operator scripts: isolation checks that compare both id spaces on purpose.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

# SQL comparisons on user_id itself are ratcheted by
# test_financial_ownership_integrity.py::test_no_backend_query_decides_by_legacy_user_id.
PATTERNS = {
    # An account found from a legacy id instead of its own id or Supabase id.
    "account_by_legacy_id": re.compile(
        r"legacy_allowed_user_id\s*(?:=|IN)\s*(?:%s|ANY|\(?\s*SELECT|[a-z_]+\.id\b)"
        r"|(?:%s|[a-z_]+\.id)\s*=\s*(?:[a-z_]+\.)?legacy_allowed_user_id\b", re.I),
    # The legacy users table (a second id space) read at runtime.
    "read_users_table": re.compile(r"\b(?:FROM|JOIN)\s+(?:public\.)?users\b", re.I),
}

REMAINING = {
    ("auth/service.py", "account_by_legacy_id"): 4,       # auth bridge
    ("auth/service.py", "read_users_table"): 2,           # auth bridge (deletion of legacy users rows)
    ("auth/workspace_context.py", "account_by_legacy_id"): 2,  # auth bridge
    ("core/user.py", "read_users_table"): 1,              # Owner-internal /ask; returns an arbitrary row
    ("email_monitor/service.py", "account_by_legacy_id"): 1,  # Owner identity
    ("email_monitor/service.py", "read_users_table"): 1,  # Owner identity
    ("integrations/ibkr_readonly.py", "account_by_legacy_id"): 1,  # Owner identity
    ("integrations/ibkr_readonly.py", "read_users_table"): 1,      # Owner identity
    ("scripts/finva_personal_isolation_check.py", "read_users_table"): 1,  # operator script
    ("scripts/set_owner_role.py", "account_by_legacy_id"): 2,  # operator script (the role lives on allowed_users)
    ("scripts/workspace_isolation_check.py", "account_by_legacy_id"): 2,   # operator script
    ("sports/service.py", "account_by_legacy_id"): 1,     # Owner identity
    ("user_product/gmail_service.py", "read_users_table"): 1,  # auth bridge (legacy users row for old FKs)
    ("user_product/service.py", "read_users_table"): 1,   # auth bridge (legacy users row for old FKs)
}


def _runtime_sources():
    for path in sorted(BACKEND.rglob("*.py")):
        relative = path.relative_to(BACKEND).as_posix()
        if relative.startswith("tests/") or path.name.startswith("test_") or "/venv/" in relative:
            continue
        yield relative, path.read_text(encoding="utf-8")


def _inventory() -> Counter:
    found: Counter = Counter()
    for relative, text in _runtime_sources():
        for name, pattern in PATTERNS.items():
            count = len(pattern.findall(text))
            if count:
                found[(relative, name)] = count
    return found


def test_no_new_reader_resolves_identity_through_a_legacy_id():
    found = _inventory()
    grown = {key: count for key, count in found.items() if count > REMAINING.get(key, 0)}
    assert not grown, (
        "New runtime code resolves identity through a legacy id. Read by account_id/workspace_id "
        f"(canonical identity) instead: {grown}"
    )


def test_the_inventory_matches_the_code():
    found = _inventory()
    stale = {key: (expected, found.get(key, 0)) for key, expected in REMAINING.items() if found.get(key, 0) != expected}
    assert not stale, f"A legacy reader was removed: lower its entry in REMAINING (expected, found): {stale}"


def test_the_patterns_recognise_what_they_guard():
    samples = {
        "account_by_legacy_id": "SELECT id FROM accounts WHERE legacy_allowed_user_id = %s",
        "read_users_table": "SELECT id FROM users WHERE lower(email)=lower(%s)",
    }
    for name, sample in samples.items():
        assert PATTERNS[name].search(sample), name
    assert PATTERNS["account_by_legacy_id"].search("JOIN accounts a ON u.id = a.legacy_allowed_user_id")
    assert PATTERNS["account_by_legacy_id"].search("WHERE legacy_allowed_user_id IN (SELECT id FROM allowed_users)")
    assert PATTERNS["read_users_table"].search("SELECT u.id FROM accounts a JOIN public.users u ON true")
    assert not PATTERNS["account_by_legacy_id"].search("SELECT legacy_allowed_user_id FROM accounts WHERE id=%s")
    assert not PATTERNS["read_users_table"].search("FROM allowed_users WHERE id = %s")
