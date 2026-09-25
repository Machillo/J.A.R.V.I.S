#!/usr/bin/env python3
"""Apply one reviewed migration, only behind a verified backup.

    python backend/scripts/apply_migration.py \
        --file database/migrations/<name>.sql --backup-dir <private dir>

Refuses unless:
  1. the file lives in database/migrations and its bytes equal the version on
     origin/main (reviewed and merged; run `git fetch origin` first);
  2. `db_backup_verify.py gate` passes for --backup-dir (BACKUP_VERIFIED,
     younger than --max-age-hours, dump hash intact);
  3. --confirm repeats the file name (no accidental runs).

The connection string comes from the variable named by --dsn-env and is never
printed. The session identifies itself as application_name 'dincr-migration'.
The migration file owns its transaction (BEGIN/COMMIT); on any error the
server rolls it back and this tool exits non-zero.
See docs/security/migration-safety-protocol.md.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import psycopg2

from backend.scripts import db_backup_verify

REPO = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO / "jarvis-personal" / "database" / "migrations"


def reviewed_content(path: Path) -> bytes:
    """The file as merged on origin/main."""
    relative = path.resolve().relative_to(REPO).as_posix()
    result = subprocess.run(["git", "-C", str(REPO), "show", f"origin/main:{relative}"], capture_output=True)
    if result.returncode != 0:
        raise SystemExit(f"{relative} is not on origin/main: only merged migrations can be applied")
    return result.stdout


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
    if not (re.search(r"^\s*BEGIN\s*;", text, re.M) and re.search(r"^\s*COMMIT\s*;", text, re.M)):
        raise SystemExit("the migration must wrap its changes in BEGIN; ... COMMIT; (no partial application)")
    if reviewed_content(path) != content:
        raise SystemExit("the local file differs from origin/main: apply only the reviewed version")
    if db_backup_verify.main(["gate", "--out", args.backup_dir, "--max-age-hours", str(args.max_age_hours)]) != 0:
        raise SystemExit("BACKUP_VERIFIED gate is closed: take and verify a backup first")

    dsn = os.environ.get(args.dsn_env, "").strip()
    if not dsn:
        raise SystemExit(f"environment variable {args.dsn_env} is empty")
    connection = psycopg2.connect(dsn, application_name="dincr-migration")
    connection.autocommit = True  # the migration file controls its own transaction
    try:
        with connection.cursor() as cur:
            cur.execute(text)
    except psycopg2.Error as error:
        print(f"FAILED {path.name}: {error.pgcode} {error.diag.message_primary}")
        return 1
    finally:
        connection.close()
    print(f"APPLIED {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
