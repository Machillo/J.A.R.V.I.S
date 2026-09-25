#!/usr/bin/env python3
"""Take a logical backup, prove it restores, and gate risky database work on it.

    backup   pg_dump the source in one exported snapshot, count every table in
             that same snapshot, restore the dump into an EMPTY scratch database
             and compare the counts. Writes <out>/<stamp>/ with the dump and
             manifest.json. Status VERIFIED only if every table matches and the
             restore raised no unexpected error.
    gate     exit 0 and print BACKUP_VERIFIED only when the newest manifest in
             <out> is VERIFIED, younger than --max-age-hours (at most 24) and its
             dump still has the recorded SHA-256. Anything else exits 2.

The manifest records the source's fingerprint (database, server address/port
and, when readable, the cluster's system identifier) and its table inventory.
apply_migration.py refuses a target whose fingerprint or tables differ, so a
backup of another database never opens the gate for production.

The dump keeps owners and privileges (GRANT/REVOKE must be recoverable); only
the scratch restore skips them.

Connection strings come from environment variables named by --source-env /
--scratch-env. They reach pg_dump/pg_restore as PG* environment variables,
never on a command line, and are never printed. The source must be a direct
(session) connection: exported snapshots do not survive a transaction pooler.
The output directory must be outside any Git repository (dumps hold personal
data); it is created 0700 and files 0600.

Read-only on the source: one REPEATABLE READ READ ONLY transaction plus
pg_dump. The only database written is the scratch one, which must be empty.
See docs/security/migration-safety-protocol.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Supported runtime: Python 3.11 (runtime.txt) with requirements.txt installed.
# Canonical invocation, from jarvis-personal/:  python3.11 -m backend.scripts.db_backup_verify ...
# Running the file directly also works: the project root is put on sys.path.
if sys.version_info < (3, 11):
    raise SystemExit(
        f"db_backup_verify needs Python 3.11 (found {sys.version.split()[0]}). From jarvis-personal/ run: "
        "python3.11 -m backend.scripts.db_backup_verify ..."
    )
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess

try:
    import psycopg2
    from psycopg2.extensions import parse_dsn
except ModuleNotFoundError as missing:  # e.g. psycopg2 or python-dotenv not installed for this interpreter
    raise SystemExit(f"db_backup_verify: missing dependency '{missing.name}'. Install jarvis-personal/requirements.txt "
                     "for Python 3.11 and run from jarvis-personal/ with python3.11 -m backend.scripts.db_backup_verify") from None

DEFAULT_SCHEMAS = ("public",)
EXIT_GATE_CLOSED = 2
MAX_GATE_AGE_HOURS = 24
# An empty database already has a public schema; that is the only restore error
# that does not affect what was restored.
BENIGN_RESTORE_ERRORS = ('schema "public" already exists',)
LIBPQ_ENV = {"host": "PGHOST", "hostaddr": "PGHOSTADDR", "port": "PGPORT", "dbname": "PGDATABASE",
             "user": "PGUSER", "password": "PGPASSWORD", "sslmode": "PGSSLMODE", "sslrootcert": "PGSSLROOTCERT",
             "connect_timeout": "PGCONNECT_TIMEOUT", "options": "PGOPTIONS"}


def _dsn(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise SystemExit(f"environment variable {env_name} is empty")
    return value


def libpq_env(dsn: str) -> dict[str, str]:
    """Connection parameters as PG* variables, so no secret reaches argv."""
    try:
        parts = parse_dsn(dsn)
    except psycopg2.ProgrammingError:
        raise SystemExit("the connection string cannot be parsed") from None
    unknown = sorted(set(parts) - set(LIBPQ_ENV) - {"application_name"})
    if unknown:
        raise SystemExit(f"unsupported connection parameters: {', '.join(unknown)}")
    if not parts.get("dbname"):
        raise SystemExit("the connection string must name a database")
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    env.update({LIBPQ_ENV[key]: value for key, value in parts.items() if key in LIBPQ_ENV})
    return env


def connect(dsn: str, application_name: str):
    try:
        return psycopg2.connect(dsn, application_name=application_name)
    except psycopg2.OperationalError:
        raise SystemExit("could not connect (details withheld: they may contain credentials)") from None


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


def fingerprint(cur) -> dict[str, str | None]:
    """Identifies the database a backup came from (no credentials)."""
    cur.execute("SELECT current_database(), host(inet_server_addr()), inet_server_port()::text")
    database, address, port = cur.fetchone()
    system_identifier = None
    cur.execute("SAVEPOINT dincr_fingerprint")
    try:
        cur.execute("SELECT system_identifier::text FROM pg_control_system()")
        system_identifier = cur.fetchone()[0]
    except psycopg2.Error:  # not granted on managed platforms
        cur.execute("ROLLBACK TO SAVEPOINT dincr_fingerprint")
    cur.execute("RELEASE SAVEPOINT dincr_fingerprint")  # pg_export_snapshot refuses subtransactions
    return {"database": database, "server_address": address, "server_port": port,
            "system_identifier": system_identifier}


def tables(cur, schemas: list[str]) -> list[str]:
    cur.execute(
        """SELECT format('%%I.%%I', n.nspname, c.relname)
           FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE c.relkind IN ('r', 'p') AND n.nspname = ANY(%s)
           ORDER BY 1""",
        (list(schemas),),
    )
    return [row[0] for row in cur.fetchall()]


def _counts(cur, names: list[str]) -> dict[str, int]:
    # With row security off, a policy raises instead of silently hiding rows.
    cur.execute("SET LOCAL row_security = off")
    counts = {}
    for table in names:
        cur.execute(f"SELECT count(*) FROM {table}")  # identifiers come from format('%I.%I')
        counts[table] = cur.fetchone()[0]
    return counts


def restore_problems(returncode: int, stderr: str) -> list[str]:
    """Why a restore cannot be trusted; empty means it can.

    Every "pg_restore: error:" must be a tolerated one, pg_restore's own count
    of ignored errors must match them, and no connection loss may appear.
    Only first lines are kept: COPY context lines can carry row values.
    """
    lines = stderr.splitlines()
    errors = [line for line in lines if line.startswith("pg_restore: error:")]
    tolerated = [line for line in errors if any(text in line for text in BENIGN_RESTORE_ERRORS)]
    problems = [line[:200] for line in errors if line not in tolerated]
    problems += [line[:200] for line in lines if re.search(r"FATAL|server closed the connection|no connection to the server", line)]
    ignored = re.search(r"errors ignored on restore: (\d+)", stderr)
    if returncode != 0 and (not tolerated or not ignored or int(ignored.group(1)) != len(tolerated)):
        problems.append(f"pg_restore exited {returncode} beyond the tolerated errors")
    return problems


def backup(args) -> int:
    os.umask(0o077)
    out = Path(args.out).expanduser().resolve()
    if _inside_git_repo(out):
        raise SystemExit("refusing to write a backup inside a Git repository")
    source_dsn, scratch_dsn = _dsn(args.source_env), _dsn(args.scratch_env)
    source_env, scratch_env = libpq_env(source_dsn), libpq_env(scratch_dsn)
    pg_dump, pg_restore = _binary("pg_dump", args.pg_bin), _binary("pg_restore", args.pg_bin)

    # Refuse before copying any production data.
    scratch = connect(scratch_dsn, "dincr-backup-restore")
    scratch.autocommit = True
    try:
        with scratch.cursor() as cur:
            if tables(cur, args.schema):
                raise SystemExit("the scratch database is not empty; restore needs an empty database")
    finally:
        scratch.close()

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    target, suffix = out / stamp, 1
    while target.exists():  # two backups within one second
        suffix += 1
        target = out / f"{stamp}-{suffix}"
    target.mkdir(mode=0o700)
    os.chmod(out, 0o700)
    dump = target / "dump.pgc"

    source = connect(source_dsn, "dincr-backup")
    source.set_session(isolation_level="REPEATABLE READ", readonly=True)
    try:
        with source.cursor() as cur:
            cur.execute("SHOW server_version")
            server_major = _major(cur.fetchone()[0])
            tool_major = _major(subprocess.run([pg_dump, "--version"], check=True, capture_output=True, text=True).stdout)
            if tool_major < server_major:
                raise SystemExit(f"pg_dump {tool_major} cannot dump server {server_major}")
            source_fingerprint = fingerprint(cur)
            cur.execute("SELECT pg_export_snapshot()")
            snapshot = cur.fetchone()[0]
            names = tables(cur, args.schema)
            if not names:
                raise SystemExit("the selected schemas contain no tables; nothing would be protected")
            source_counts = _counts(cur, names)
            result = subprocess.run(
                [pg_dump, "--format=custom", "--strict-names", f"--snapshot={snapshot}", f"--file={dump}",
                 *[f"--schema={schema}" for schema in args.schema]],
                capture_output=True, text=True, env=source_env,
            )
            if result.returncode != 0:
                last = (result.stderr.strip().splitlines() or ["no output"])[-1]
                raise SystemExit("pg_dump failed: " + last[:200])
    finally:
        source.rollback()
        source.close()
    os.chmod(dump, 0o600)

    result = subprocess.run([pg_restore, "--no-owner", "--no-privileges", f"--dbname={scratch_env['PGDATABASE']}", str(dump)],
                            capture_output=True, text=True, env=scratch_env)
    problems = restore_problems(result.returncode, result.stderr)
    scratch = connect(scratch_dsn, "dincr-backup-restore")
    try:
        with scratch.cursor() as cur:
            restored_counts = _counts(cur, tables(cur, args.schema))
        scratch.rollback()
    finally:
        scratch.close()

    mismatches = {table: {"source": count, "restored": restored_counts.get(table)}
                  for table, count in source_counts.items() if restored_counts.get(table) != count}
    status = "VERIFIED" if not mismatches and not problems else "FAILED"
    manifest = {
        "status": status,
        "created_at": stamp,
        "source": source_fingerprint,
        "server_major": server_major,
        "pg_dump_major": tool_major,
        "schemas": list(args.schema),
        "dump_file": dump.name,
        "dump_sha256": _sha256(dump),
        "dump_bytes": dump.stat().st_size,
        "tables": len(source_counts),
        "rows": sum(source_counts.values()),
        "row_counts": source_counts,
        "mismatches": mismatches,
        "restore_exit_code": result.returncode,
        "restore_problems": problems,
    }
    manifest_path = target / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(manifest_path, 0o600)
    print(f"{status}: {len(source_counts)} tables, {manifest['rows']} rows, {target}")
    return 0 if status == "VERIFIED" else 1


def verified_manifest(out, max_age_hours: float) -> dict:
    """The newest backup if it opens the gate; SystemExit(reason) otherwise."""
    if not 0 <= max_age_hours <= MAX_GATE_AGE_HOURS:
        raise SystemExit(f"--max-age-hours must be between 0 and {MAX_GATE_AGE_HOURS}")
    folder = Path(out).expanduser().resolve()
    manifests = sorted(folder.glob("*/manifest.json")) if folder.is_dir() else []
    if not manifests:
        raise SystemExit("no backup manifest")
    manifest_path = manifests[-1]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    created = dt.datetime.strptime(manifest["created_at"], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
    age_hours = (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 3600
    dump = manifest_path.parent / manifest["dump_file"]
    problems = []
    if manifest.get("status") != "VERIFIED":
        problems.append(f"newest backup status is {manifest.get('status')}")
    if not 0 <= age_hours <= max_age_hours:
        problems.append(f"newest backup is {age_hours:.1f} h old (limit {max_age_hours} h)")
    if not dump.is_file() or _sha256(dump) != manifest.get("dump_sha256"):
        problems.append("dump file missing or its SHA-256 changed")
    if problems:
        raise SystemExit("; ".join(problems))
    return manifest


def gate(args) -> int:
    try:
        manifest = verified_manifest(args.out, args.max_age_hours)
    except SystemExit as closed:
        print(f"GATE CLOSED: {closed}")
        return EXIT_GATE_CLOSED
    print(f"BACKUP_VERIFIED {manifest['created_at']} database={manifest['source']['database']} "
          f"tables={manifest['tables']} rows={manifest['rows']} sha256={manifest['dump_sha256']}")
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
