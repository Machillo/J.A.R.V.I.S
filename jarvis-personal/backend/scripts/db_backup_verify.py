#!/usr/bin/env python3
"""Take a logical backup, prove it restores, and gate risky database work on it.

    backup   pg_dump the source in one exported snapshot, count every table in
             that same snapshot, restore the dump into an EMPTY scratch database
             and compare the counts. Writes <out>/<stamp>/ with the dump,
             manifest.json and SHA-256; status VERIFIED only if every table
             matches.
    gate     exit 0 and print BACKUP_VERIFIED only when the newest manifest in
             <out> is VERIFIED, younger than --max-age-hours and its dump still
             has the recorded SHA-256. Anything else exits 2.

Connection strings are read from environment variables named by --source-env /
--scratch-env and are never printed. The source must be a direct (session)
connection: exported snapshots do not survive a transaction pooler. The output
directory must be outside any Git repository (dumps hold personal data); it is
created 0700 and files 0600.

Read-only on the source: one REPEATABLE READ READ ONLY transaction plus
pg_dump. The only database written is the scratch one, which must be empty.
See docs/security/migration-safety-protocol.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg2

DEFAULT_SCHEMAS = ("public",)
EXIT_GATE_CLOSED = 2
# An empty database already has a public schema; that is the only restore error
# that does not affect what was restored.
BENIGN_RESTORE_ERRORS = ('schema "public" already exists',)


def _dsn(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise SystemExit(f"environment variable {env_name} is empty")
    return value


def _binary(name: str, bin_dir: str | None) -> str:
    path = shutil.which(name, path=bin_dir) if bin_dir else shutil.which(name)
    if not path:
        raise SystemExit(f"{name} not found (use --pg-bin)")
    return path


def _major(version_text: str) -> int:
    match = re.search(r"(\d+)(?:\.\d+)?", version_text)
    if not match:
        raise SystemExit(f"cannot read a PostgreSQL version from {version_text!r}")
    return int(match.group(1))


def _inside_git_repo(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in (path, *path.parents))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _tables(cur, schemas: list[str]) -> list[str]:
    cur.execute(
        """SELECT format('%%I.%%I', n.nspname, c.relname)
           FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE c.relkind IN ('r', 'p') AND n.nspname = ANY(%s)
           ORDER BY 1""",
        (schemas,),
    )
    return [row[0] for row in cur.fetchall()]


def _counts(cur, tables: list[str]) -> dict[str, int]:
    counts = {}
    for table in tables:
        cur.execute(f"SELECT count(*) FROM {table}")  # identifiers come from format('%I.%I')
        counts[table] = cur.fetchone()[0]
    return counts


def backup(args) -> int:
    out = Path(args.out).expanduser().resolve()
    if _inside_git_repo(out):
        raise SystemExit("refusing to write a backup inside a Git repository")
    source_dsn, scratch_dsn = _dsn(args.source_env), _dsn(args.scratch_env)
    pg_dump, pg_restore = _binary("pg_dump", args.pg_bin), _binary("pg_restore", args.pg_bin)

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = out / stamp
    target.mkdir(parents=True, mode=0o700)
    os.chmod(out, 0o700)
    dump = target / "dump.pgc"

    source = psycopg2.connect(source_dsn, application_name="dincr-backup")
    source.set_session(isolation_level="REPEATABLE READ", readonly=True)
    try:
        with source.cursor() as cur:
            cur.execute("SHOW server_version")
            server_major = _major(cur.fetchone()[0])
            tool_major = _major(subprocess.run([pg_dump, "--version"], check=True, capture_output=True, text=True).stdout)
            if tool_major < server_major:
                raise SystemExit(f"pg_dump {tool_major} cannot dump server {server_major}")
            cur.execute("SELECT pg_export_snapshot()")
            snapshot = cur.fetchone()[0]
            tables = _tables(cur, args.schema)
            source_counts = _counts(cur, tables)
            command = [pg_dump, "--format=custom", "--no-owner", "--no-privileges", f"--snapshot={snapshot}",
                       f"--file={dump}", *[f"--schema={schema}" for schema in args.schema], source_dsn]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                raise SystemExit("pg_dump failed:\n" + result.stderr.replace(source_dsn, "<source>"))
    finally:
        source.rollback()
        source.close()
    os.chmod(dump, 0o600)

    scratch = psycopg2.connect(scratch_dsn, application_name="dincr-backup-restore")
    scratch.autocommit = True
    try:
        with scratch.cursor() as cur:
            if _tables(cur, args.schema):
                raise SystemExit("the scratch database is not empty; restore needs an empty database")
        result = subprocess.run([pg_restore, "--no-owner", "--no-privileges", f"--dbname={scratch_dsn}", str(dump)],
                                capture_output=True, text=True)
        restore_errors = result.stderr.replace(scratch_dsn, "<scratch>").strip()
        with scratch.cursor() as cur:
            restored_counts = _counts(cur, _tables(cur, args.schema))
    finally:
        scratch.close()

    mismatches = {table: {"source": count, "restored": restored_counts.get(table)}
                  for table, count in source_counts.items() if restored_counts.get(table) != count}
    errors = [line for line in restore_errors.splitlines() if "ERROR:" in line]
    unexpected_errors = [line for line in errors if not any(benign in line for benign in BENIGN_RESTORE_ERRORS)]
    status = "VERIFIED" if not mismatches and not unexpected_errors and (result.returncode == 0 or errors) else "FAILED"
    manifest = {
        "status": status,
        "created_at": stamp,
        "server_major": server_major,
        "pg_dump_major": tool_major,
        "schemas": args.schema,
        "dump_file": dump.name,
        "dump_sha256": _sha256(dump),
        "dump_bytes": dump.stat().st_size,
        "tables": len(source_counts),
        "rows": sum(source_counts.values()),
        "row_counts": source_counts,
        "mismatches": mismatches,
        "restore_exit_code": result.returncode,
        "restore_unexpected_errors": unexpected_errors,
        "restore_errors": restore_errors[-4000:],
    }
    manifest_path = target / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(manifest_path, 0o600)
    print(f"{status}: {len(source_counts)} tables, {manifest['rows']} rows, {target}")
    return 0 if status == "VERIFIED" else 1


def gate(args) -> int:
    out = Path(args.out).expanduser().resolve()
    manifests = sorted(out.glob("*/manifest.json")) if out.is_dir() else []
    if not manifests:
        print("GATE CLOSED: no backup manifest")
        return EXIT_GATE_CLOSED
    manifest_path = manifests[-1]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    created = dt.datetime.strptime(manifest["created_at"], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
    age_hours = (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 3600
    dump = manifest_path.parent / manifest["dump_file"]
    problems = []
    if manifest.get("status") != "VERIFIED":
        problems.append(f"newest backup status is {manifest.get('status')}")
    if age_hours > args.max_age_hours:
        problems.append(f"newest backup is {age_hours:.1f} h old (limit {args.max_age_hours} h)")
    if not dump.is_file() or _sha256(dump) != manifest.get("dump_sha256"):
        problems.append("dump file missing or its SHA-256 changed")
    if problems:
        print("GATE CLOSED: " + "; ".join(problems))
        return EXIT_GATE_CLOSED
    print(f"BACKUP_VERIFIED {manifest['created_at']} tables={manifest['tables']} rows={manifest['rows']} sha256={manifest['dump_sha256']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("backup")
    make.add_argument("--out", required=True)
    make.add_argument("--source-env", default="DINCR_BACKUP_SOURCE_DSN")
    make.add_argument("--scratch-env", default="DINCR_BACKUP_SCRATCH_DSN")
    make.add_argument("--pg-bin", default=None, help="directory with pg_dump/pg_restore")
    make.add_argument("--schema", action="append", default=None,
                      help="schema to back up and verify (repeatable; default: public)")
    check = sub.add_parser("gate")
    check.add_argument("--out", required=True)
    check.add_argument("--max-age-hours", type=float, default=6)
    args = parser.parse_args(argv)
    if args.command == "backup":
        args.schema = args.schema or list(DEFAULT_SCHEMAS)
    return backup(args) if args.command == "backup" else gate(args)


if __name__ == "__main__":
    sys.exit(main())
