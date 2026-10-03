"""Owner-only category compatibility (CLAUDE.md §4.A; master plan P0.1).

The DINCR Owner's historical records use a few aliases that are personal to that account,
not part of the product: family words, specific destinations, standalone bank words that
are ambiguous as plain text, and generic stock words that meant the Owner's own broker.
They keep resolving for the Owner, and only for the Owner:

- `backend.finance.category_catalog` resolves the neutral catalog by default and merges
  these entries only when the caller passes `owner=True`;
- callers decide that from the server's own records, never from anything a client sends:
  `category_catalog.owner_context()` (the verified session role) in Owner-only modules, and
  `category_catalog.owner_account_context()` (the stored Owner identity of the account and
  workspace whose data is processed) in the shared pipelines, including background sync.

This is the single Owner, not a multi-owner feature: there is no per-account alias
administration, and no plan or request field can turn it on.
"""
from __future__ import annotations

from typing import Any

# Categories that exist for the Owner only (none today: IBKR is a shared institution).
OWNER_ONLY_CATEGORIES: list[dict[str, Any]] = []

# Owner aliases for categories of the neutral catalog: removed from the neutral matching
# because they are personal (family words, specific destinations) or ambiguous as plain text
# ("bac", "popular", "familia").
OWNER_EXTRA_ALIASES: dict[str, list[str]] = {
    "Tarjeta BAC": ["bac"],
    "Banco Popular": ["popular"],
    "Familiar": ["familia", "papa", "papá", "mama", "mamá"],
    "Viajes": ["ecuador", "japon", "japón", "mexico", "méxico"],
    # Generic stock words: "Otros" for everyone else; the Owner's own broker for him.
    "IBKR": ["acciones", "bolsa"],
}


def owner_transfer_category(clean_text: str) -> str | None:
    """The Owner's historical rule for a family transfer: "Familiar".

    Kept exactly as the shared parser applied it before P0.1 (a substring of the
    normalized text), so the Owner's mail resolves as it always did.
    """
    clean = clean_text or ""
    return "Familiar" if "papa" in clean or "papá" in clean else None
