"""Owner-only category compatibility (CLAUDE.md §4.A; master plan P0.1).

The DINCR Owner's historical records use a few aliases and one category that are personal
to that account, not part of the product: family words, specific destinations, standalone
bank words that are ambiguous as plain text, and a broker used as an investment category.
They keep resolving for the Owner, and only for the Owner:

- `backend.finance.category_catalog` resolves the neutral catalog by default and merges
  these entries only when the caller passes `owner=True`;
- callers decide that from the server's role (`category_catalog.owner_context()`), never
  from anything a client sends.

This is the single Owner, not a multi-owner feature: there is no per-account alias
administration, and no plan or request field can turn it on.
"""
from __future__ import annotations

from typing import Any

# Categories that exist for the Owner only. Users' generic equivalents live in the neutral
# catalog (investment words resolve to "Otros" in INVERSIONES).
OWNER_ONLY_CATEGORIES: list[dict[str, Any]] = [
    {"group_name": "INVERSIONES", "category_name": "IBKR", "transaction_type": "transfer", "sort_order": 510,
     "aliases": ["ibkr", "interactive brokers", "acciones", "bolsa"]},
]

# Owner aliases for categories of the neutral catalog: removed from the neutral matching
# because they are personal (family words, specific destinations) or ambiguous as plain text
# ("bac", "popular", "familia").
OWNER_EXTRA_ALIASES: dict[str, list[str]] = {
    "Tarjeta BAC": ["bac"],
    "Banco Popular": ["popular"],
    "Familiar": ["familia", "papa", "papá", "mama", "mamá"],
    "Viajes": ["ecuador", "japon", "japón", "mexico", "méxico"],
}


def owner_transfer_category(clean_text: str) -> str | None:
    """The Owner's historical rule for a family transfer: "Familiar".

    Kept exactly as the shared parser applied it before P0.1 (a substring of the
    normalized text), so the Owner's mail resolves as it always did.
    """
    clean = clean_text or ""
    return "Familiar" if "papa" in clean or "papá" in clean else None
