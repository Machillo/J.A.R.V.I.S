"""The backup tool proves a restore before it opens the gate (real PostgreSQL)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.scripts import db_backup_verify as tool  # noqa: E402

PG_BIN = str(Path(pgserver.__file__).parent / "pginstall" / "bin")


@pytest.fixture
def databases(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    suffix = abs(hash(str(tmp_path))) % 10**8
    names = {"source": f"bk_src_{suffix}", "scratch": f"bk_scr_{suffix}"}
    with admin.cursor() as cur:
        for name in names.values():
            cur.execute(f"CREATE DATABASE {name}")
    source = psycopg2.connect(server.get_uri(names["source"]))
    source.autocommit = True
    with source.cursor() as cur:
        cur.execute("CREATE TABLE ledger (id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, amount NUMERIC)")
        cur.execute("CREATE TABLE notes (id INT PRIMARY KEY, body TEXT)")
        cur.execute("INSERT INTO ledger(workspace_id, amount) SELECT gen_random_uuid(), g FROM generate_series(1, 25) g")
        cur.execute("INSERT INTO notes VALUES (1, 'synthetic')")
    source.close()
    monkeypatch.setenv("SRC_DSN", server.get_uri(names["source"]))
    monkeypatch.setenv("SCR_DSN", server.get_uri(names["scratch"]))
    yield server, names
    with admin.cursor() as cur:
        for name in names.values():
            cur.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
    admin.close()


def _backup(out: Path) -> int:
    return tool.main(["backup", "--out", str(out), "--source-env", "SRC_DSN", "--scratch-env", "SCR_DSN", "--pg-bin", PG_BIN])


def test_backup_is_verified_by_a_real_restore_and_opens_the_gate(databases, tmp_path, capsys):
    out = tmp_path / "backups"
    assert _backup(out) == 0

    manifest = json.loads(next(out.glob("*/manifest.json")).read_text())
    assert manifest["status"] == "VERIFIED"
    assert manifest["row_counts"] == {"public.ledger": 25, "public.notes": 1}
    assert oct(out.stat().st_mode & 0o777) == "0o700"
    assert oct(next(out.glob("*/dump.pgc")).stat().st_mode & 0o777) == "0o600"
    assert tool.main(["gate", "--out", str(out)]) == 0
    assert "BACKUP_VERIFIED" in capsys.readouterr().out


def test_gate_closes_when_the_dump_changes(databases, tmp_path):
    out = tmp_path / "backups"
    assert _backup(out) == 0
    dump = next(out.glob("*/dump.pgc"))
    dump.write_bytes(dump.read_bytes() + b"tampered")

    assert tool.main(["gate", "--out", str(out)]) == tool.EXIT_GATE_CLOSED


def test_gate_closes_when_the_backup_is_too_old(databases, tmp_path):
    out = tmp_path / "backups"
    assert _backup(out) == 0

    assert tool.main(["gate", "--out", str(out), "--max-age-hours", "0"]) == tool.EXIT_GATE_CLOSED


def test_gate_closes_without_any_backup(tmp_path):
    assert tool.main(["gate", "--out", str(tmp_path / "none")]) == tool.EXIT_GATE_CLOSED


def test_restore_never_writes_into_a_non_empty_database(databases, tmp_path):
    server, names = databases
    scratch = psycopg2.connect(server.get_uri(names["scratch"]))
    scratch.autocommit = True
    with scratch.cursor() as cur:
        cur.execute("CREATE TABLE keep (id INT)")
    scratch.close()

    with pytest.raises(SystemExit, match="not empty"):
        _backup(tmp_path / "backups")


def test_a_backup_never_lands_inside_a_git_repository():
    with pytest.raises(SystemExit, match="Git repository"):
        tool.main(["backup", "--out", str(Path(__file__).parent / "never"), "--source-env", "SRC_DSN"])


def test_a_restore_that_loses_a_table_is_failed_and_keeps_the_gate_closed(databases, tmp_path):
    server, names = databases
    source = psycopg2.connect(server.get_uri(names["source"]))
    source.autocommit = True
    with source.cursor() as cur:
        # Supabase-like: a public table depends on an object outside the dumped schemas.
        cur.execute("CREATE SCHEMA extensions; CREATE DOMAIN extensions.amount AS NUMERIC")
        cur.execute("CREATE TABLE balances (id INT PRIMARY KEY, value extensions.amount)")
        cur.execute("INSERT INTO balances VALUES (1, 10)")
    source.close()
    out = tmp_path / "backups"

    assert _backup(out) == 1
    manifest = json.loads(next(out.glob("*/manifest.json")).read_text())
    assert manifest["status"] == "FAILED"
    assert manifest["mismatches"]["public.balances"] == {"source": 1, "restored": None}
    assert tool.main(["gate", "--out", str(out)]) == tool.EXIT_GATE_CLOSED


def test_including_the_dependency_schema_makes_the_same_backup_verifiable(databases, tmp_path):
    server, names = databases
    source = psycopg2.connect(server.get_uri(names["source"]))
    source.autocommit = True
    with source.cursor() as cur:
        cur.execute("CREATE SCHEMA extensions; CREATE DOMAIN extensions.amount AS NUMERIC")
        cur.execute("CREATE TABLE balances (id INT PRIMARY KEY, value extensions.amount)")
        cur.execute("INSERT INTO balances VALUES (1, 10)")
    source.close()
    out = tmp_path / "backups"

    assert tool.main(["backup", "--out", str(out), "--source-env", "SRC_DSN", "--scratch-env", "SCR_DSN",
                      "--pg-bin", PG_BIN, "--schema", "public", "--schema", "extensions"]) == 0
    assert tool.main(["gate", "--out", str(out)]) == 0
