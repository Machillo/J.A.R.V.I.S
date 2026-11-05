"""Real personal data does not belong in this repository (CLAUDE.md §4 F).

The checked names are stored only as hashes, so this guard does not itself publish them.
"""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ("backend", "database/migrations", "docs", "native", "frontend/src", "store-assets/copy")
SUFFIXES = {".py", ".sql", ".md", ".json", ".kt", ".swift", ".js", ".jsx", ".mjs"}
FORBIDDEN_WORD_HASHES = {"e8e9689deac5bac9", "1b6930f523bfe596"}
WORD = re.compile(r"[a-záéíóúñü]+")


def _files():
    for folder in SCANNED:
        for path in (ROOT / folder).rglob("*"):
            if path.suffix in SUFFIXES and path.is_file() and "node_modules" not in path.parts and "build" not in path.parts:
                yield path


def _hash(word: str) -> str:
    return hashlib.sha256(word.encode()).hexdigest()[:16]


def test_third_party_names_are_not_in_the_repository():
    found = []
    for path in _files():
        words = set(WORD.findall(path.read_text(encoding="utf-8", errors="ignore").lower()))
        if any(_hash(word) in FORBIDDEN_WORD_HASHES for word in words):
            found.append(str(path.relative_to(ROOT)))
    assert not found


def test_migrations_do_not_rewrite_one_specific_account():
    specific = re.compile(r"WHERE\s+user_id\s*=\s*\d+|account_last4\s*=\s*'\d{4}'", re.I)
    found = [path.name for path in (ROOT / "database/migrations").glob("*.sql") if specific.search(path.read_text(encoding="utf-8"))]
    assert not found


def test_owner_personal_seed_is_gone():
    from backend.finance import fixed_expenses

    assert not hasattr(fixed_expenses, "seed_owner_fixed_expenses")
