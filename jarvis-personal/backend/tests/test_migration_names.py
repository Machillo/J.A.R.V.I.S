"""Migration file names identify one migration each.

apply_migration.py applies one named file and its ledger dedupes by content, so it
would accept two migrations sharing a timestamp. People, reviews and PR guards
refer to migrations by timestamp, so a shared one is ambiguous (e.g. an unrelated
migration reusing the timestamp of one already applied in production). Timestamped
names (YYYYMMDDHHMMSS) are unique; date-only names (YYYYMMDD) are the legacy ones,
which share days and are all applied, and no new one may be added.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

DATABASE = Path(__file__).resolve().parents[2] / "database"
NAME = re.compile(r"(?P<stamp>\d{14}|\d{8})_[a-z0-9_]+\.sql")
LAST_DATE_ONLY_DAY = "20260923"  # the last legacy date-only migration; later ones are timestamped


def name_problems(names: list[str]) -> list[str]:
    problems = [f"not <timestamp>_<name>.sql: {name}" for name in names if not NAME.fullmatch(name)]
    stamps = Counter(match["stamp"] for match in map(NAME.fullmatch, names) if match and len(match["stamp"]) == 14)
    problems += [f"timestamp {stamp} is used by {count} migrations" for stamp, count in sorted(stamps.items()) if count > 1]
    problems += [f"new date-only name (use YYYYMMDDHHMMSS): {name}" for name in names
                 if (match := NAME.fullmatch(name)) and len(match["stamp"]) == 8 and match["stamp"] > LAST_DATE_ONLY_DAY]
    return problems


def orphan_rollbacks(migrations: list[str], rollbacks: list[str]) -> list[str]:
    stems = {name.removesuffix(".sql") for name in migrations}
    return [name for name in rollbacks
            if not name.endswith("_rollback.sql") or name.removesuffix("_rollback.sql") not in stems]


def _names(folder: str) -> list[str]:
    return sorted(path.name for path in (DATABASE / folder).iterdir() if path.is_file())


def test_every_migration_has_its_own_timestamp():
    assert name_problems(_names("migrations")) == []


def test_every_rollback_belongs_to_a_migration():
    assert orphan_rollbacks(_names("migrations"), _names("rollback")) == []


def test_the_checks_see_what_they_guard():
    assert name_problems(["20260926150000_dincr_app_role.sql", "20260926150000_other_change.sql"]) == [
        "timestamp 20260926150000 is used by 2 migrations"]
    assert name_problems(["20260902_a.sql", "20260902_b.sql"]) == []  # legacy date-only days may repeat
    assert name_problems(["20261001_new.sql"]) == ["new date-only name (use YYYYMMDDHHMMSS): 20261001_new.sql"]
    assert name_problems(["2026_bad.sql", "20260928110000_Upper.sql", "20260928110000_x.txt"]) == [
        "not <timestamp>_<name>.sql: 2026_bad.sql", "not <timestamp>_<name>.sql: 20260928110000_Upper.sql",
        "not <timestamp>_<name>.sql: 20260928110000_x.txt"]
    assert orphan_rollbacks(["20260928110000_x.sql"], ["20260928110000_x_rollback.sql", "20260926150000_x_rollback.sql",
                                                       "notes.sql"]) == ["20260926150000_x_rollback.sql", "notes.sql"]
