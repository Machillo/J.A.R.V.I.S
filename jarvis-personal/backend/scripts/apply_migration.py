#!/usr/bin/env python3
"""Apply one reviewed migration, only behind a verified backup of the same database.

    python3.11 -m backend.scripts.apply_migration \
        --file database/migrations/<name>.sql --backup-dir <private dir> --confirm <name>.sql

Refuses unless:
  1. the file lives in database/migrations and its bytes equal the version on
     origin/main, fetched now (reviewed and merged);
  2. it is exactly one transaction: BEGIN first, COMMIT last, no other
     transaction control (comments and quoted text are ignored when checking);
  3. `db_backup_verify.py gate` would open for --backup-dir, and the target has
     the same fingerprint and table inventory as that backup's source;
  4. this file (by SHA-256) was not already applied to this database from the
     same backup directory (ledger: <backup-dir>/applied.jsonl);
  5. --confirm repeats the file name.

The connection string comes from the variable named by --dsn-env and is never
printed; errors print only their SQLSTATE. The session is named
'dincr-migration' and has a default lock_timeout of 5 s (a migration's own
SET LOCAL wins). If the transaction is not closed by the file's COMMIT, it is
rolled back and reported as FAILED.
See docs/security/migration-safety-protocol.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Supported runtime: Python 3.11 (runtime.txt) with requirements.txt installed.
# Canonical invocation, from jarvis-personal/:  python3.11 -m backend.scripts.apply_migration ...
# Running the file directly also works: the project root is put on sys.path.
if sys.version_info < (3, 11):
    raise SystemExit(
        f"apply_migration needs Python 3.11 (found {sys.version.split()[0]}). From jarvis-personal/ run: "
        "python3.11 -m backend.scripts.apply_migration ..."
    )
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess

try:
    import psycopg2
    from psycopg2 import extensions
    from backend.scripts import db_backup_verify
except ModuleNotFoundError as missing:  # e.g. psycopg2 or python-dotenv not installed for this interpreter
    raise SystemExit(f"apply_migration: cannot import '{missing.name}'. Run it from the jarvis-personal/ checkout with "
                     "Python 3.11 and requirements.txt installed: python3.11 -m backend.scripts.apply_migration") from None

REPO = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO / "jarvis-personal" / "database" / "migrations"
TRANSACTION_CONTROL = re.compile(r"^(BEGIN|START\s+TRANSACTION|COMMIT|END|ROLLBACK|ABORT|SAVEPOINT|RELEASE|PREPARE\s+TRANSACTION)\b", re.I)


def statements(sql: str) -> list[str]:
    """Top-level statements with comments removed (quotes and dollar quotes respected)."""
    result, current, index, length = [], [], 0, len(sql)
    while index < length:
        char = sql[index]
        if sql.startswith("--", index):
            end = sql.find("\n", index)
            index = length if end < 0 else end
            continue
        if sql.startswith("/*", index):
            depth, index = 1, index + 2
            while index < length and depth:
                if sql.startswith("/*", index):
                    depth, index = depth + 1, index + 2
                elif sql.startswith("*/", index):
                    depth, index = depth - 1, index + 2
                else:
                    index += 1
            current.append(" ")
            continue
        if char in ("'", '"'):
            end = index + 1
            while end < length:
                if sql[end] == char and sql.startswith(char * 2, end):
                    end += 2
                elif sql[end] == char:
                    break
                else:
                    end += 1
            current.append(sql[index:end + 1])
            index = end + 1
            continue
        dollar = re.match(r"\$[A-Za-z_]*\$", sql[index:])
        if dollar:
            tag = dollar.group(0)
            end = sql.find(tag, index + len(tag))
            end = length if end < 0 else end + len(tag)
            current.append(sql[index:end])
            index = end
            continue
        if char == ";":
            text = " ".join("".join(current).split())
            if text:
                result.append(text)
            current = []
        else:
            current.append(char)
        index += 1
    text = " ".join("".join(current).split())
    if text:
        result.append(text)
    return result


def check_single_transaction(sql: str) -> None:
    parts = statements(sql)
    if len(parts) < 2 or not re.fullmatch(r"(BEGIN|START\s+TRANSACTION)( .*)?", parts[0], re.I) \
            or not re.fullmatch(r"(COMMIT|END)( .*)?", parts[-1], re.I):
        raise SystemExit("the migration must be exactly one transaction: BEGIN; ... COMMIT; with nothing after COMMIT")
    inner = [part for part in parts[1:-1] if TRANSACTION_CONTROL.match(part)]
    if inner:
        raise SystemExit(f"transaction control inside the migration is not allowed: {inner[0][:40]}")


def reviewed_content(path: Path) -> tuple[bytes, str]:
    """The file as merged on origin/main right now, and that commit."""
    fetch = subprocess.run(["git", "-C", str(REPO), "fetch", "--quiet", "origin", "main"], capture_output=True)
    if fetch.returncode != 0:
        raise SystemExit("could not fetch origin/main; the reviewed version cannot be confirmed")
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "origin/main"], capture_output=True, text=True, check=True).stdout.strip()
    relative = path.resolve().relative_to(REPO).as_posix()
    shown = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True)
    if shown.returncode != 0:
        raise SystemExit(f"{relative} is not on origin/main: only merged migrations can be applied")
    return shown.stdout, commit


def _ledger(backup_dir: Path) -> Path:
    return Path(backup_dir).expanduser().resolve() / "applied.jsonl"


def already_applied(backup_dir: Path, source: dict, file_sha: str) -> bool:
    ledger = _ledger(backup_dir)
    if not ledger.is_file():
        return False
    for line in ledger.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry.get("sha256") == file_sha and entry.get("source") == source:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--max-age-hours", type=float, default=6)
    parser.add_argument("--dsn-env", default="DINCR_MIGRATION_DSN")
    parser.add_argument("--confirm", required=True, help="repeat the migration file name")
    args = parser.parse_args(argv)

    path = Path(args.file).resolve()
    if path.parent != MIGRATIONS.resolve() or path.suffix != ".sql":
        raise SystemExit("only files in database/migrations can be applied")
    if args.confirm != path.name:
        raise SystemExit("--confirm must repeat the migration file name")
    content = path.read_bytes()
    text = content.decode("utf-8")
    check_single_transaction(text)
    reviewed, main_commit = reviewed_content(path)
    if reviewed != content:
        raise SystemExit("the local file differs from origin/main: apply only the reviewed version")
    file_sha = hashlib.sha256(content).hexdigest()
    try:
        manifest = db_backup_verify.verified_manifest(args.backup_dir, args.max_age_hours)
    except SystemExit as closed:
        raise SystemExit(f"BACKUP_VERIFIED gate is closed: {closed}") from None

    dsn = os.environ.get(args.dsn_env, "").strip()
    if not dsn:
        raise SystemExit(f"environment variable {args.dsn_env} is empty")
    connection = db_backup_verify.connect(dsn, "dincr-migration")
    try:
        with connection.cursor() as cur:
            target = db_backup_verify.fingerprint(cur)
            if target != manifest["source"]:
                raise SystemExit("the verified backup was taken from a different database than the target")
            target_tables = set(db_backup_verify.tables(cur, manifest["schemas"]))
            if target_tables != set(manifest["row_counts"]):
                raise SystemExit("the target's tables differ from the verified backup; take a new backup")
        connection.rollback()
        if already_applied(Path(args.backup_dir), target, file_sha):
            raise SystemExit("this migration was already applied to this database")

        connection.autocommit = True  # the migration file owns its single transaction
        with connection.cursor() as cur:
            cur.execute("SET lock_timeout = '5s'")
            try:
                cur.execute(text)
            except psycopg2.Error as error:
                print(f"FAILED {path.name}: SQLSTATE {error.pgcode} (nothing was applied)")
                return 1
        if connection.info.transaction_status != extensions.TRANSACTION_STATUS_IDLE:
            connection.rollback()
            print(f"FAILED {path.name}: the transaction was left open and has been rolled back")
            return 1
    finally:
        connection.close()

    entry = {"file": path.name, "sha256": file_sha, "main_commit": main_commit, "source": target,
             "backup": manifest["created_at"], "applied_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    ledger = _ledger(Path(args.backup_dir))
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    os.chmod(ledger, 0o600)
    print(f"APPLIED {path.name} sha256={file_sha} main={main_commit} backup={manifest['created_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
