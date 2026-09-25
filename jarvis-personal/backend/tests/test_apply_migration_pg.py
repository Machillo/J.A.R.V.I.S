"""apply_migration.py applies only reviewed SQL, only behind BACKUP_VERIFIED."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.scripts import apply_migration, db_backup_verify  # noqa: E402

PG_BIN = str(Path(pgserver.__file__).parent / "pginstall" / "bin")
MIGRATION = "BEGIN;\nCREATE TABLE applied_marker (id INT);\nCOMMIT;\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    suffix = abs(hash(str(tmp_path))) % 10**8
    target, scratch = f"am_tgt_{suffix}", f"am_scr_{suffix}"
    with admin.cursor() as cur:
        cur.execute(f"CREATE DATABASE {target}")
        cur.execute(f"CREATE DATABASE {scratch}")
    seed = psycopg2.connect(server.get_uri(target))
    seed.autocommit = True
    with seed.cursor() as cur:
        cur.execute("CREATE TABLE existing_ledger (id INT PRIMARY KEY); INSERT INTO existing_ledger VALUES (1)")
    seed.close()
    monkeypatch.setenv("DINCR_MIGRATION_DSN", server.get_uri(target))
    monkeypatch.setenv("SRC_DSN", server.get_uri(target))
    monkeypatch.setenv("SCR_DSN", server.get_uri(scratch))
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    reviewed: dict[str, bytes] = {}
    monkeypatch.setattr(apply_migration, "MIGRATIONS", migrations)
    def reviewed_content(path):
        if path.name not in reviewed:
            raise SystemExit("not on origin/main")
        return reviewed[path.name], "0" * 40

    monkeypatch.setattr(apply_migration, "reviewed_content", reviewed_content)
    monkeypatch.setenv("OTHER_DSN", server.get_uri(scratch))
    def reset_scratch():
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE {scratch} WITH (FORCE)")
            cur.execute(f"CREATE DATABASE {scratch}")

    yield {"server": server, "target": target, "scratch": scratch, "reset_scratch": reset_scratch, "migrations": migrations, "reviewed": reviewed, "backups": tmp_path / "backups"}
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {target} WITH (FORCE)")
        cur.execute(f"DROP DATABASE IF EXISTS {scratch} WITH (FORCE)")
    admin.close()


def _write(env, name: str, sql: str, *, merged: bool = True) -> Path:
    path = env["migrations"] / name
    path.write_text(sql, encoding="utf-8")
    if merged:
        env["reviewed"][name] = sql.encode("utf-8")
    return path


def _backup(env) -> None:
    assert db_backup_verify.main(["backup", "--out", str(env["backups"]), "--source-env", "SRC_DSN",
                                  "--scratch-env", "SCR_DSN", "--pg-bin", PG_BIN]) == 0


def _apply(env, path: Path) -> int:
    return apply_migration.main(["--file", str(path), "--backup-dir", str(env["backups"]), "--confirm", path.name])


def _exists(env, table: str) -> bool:
    conn = psycopg2.connect(env["server"].get_uri(env["target"]))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",))
            return cur.fetchone()[0]
    finally:
        conn.close()


def test_refuses_without_a_verified_backup(env):
    path = _write(env, "001_marker.sql", MIGRATION)

    with pytest.raises(SystemExit, match="BACKUP_VERIFIED gate is closed"):
        _apply(env, path)
    assert not _exists(env, "applied_marker")


def test_refuses_a_file_that_is_not_the_merged_version(env):
    path = _write(env, "001_marker.sql", MIGRATION, merged=False)
    _backup(env)

    with pytest.raises(SystemExit, match="origin/main"):
        _apply(env, path)
    assert not _exists(env, "applied_marker")


def test_refuses_a_migration_without_its_own_transaction(env):
    path = _write(env, "001_marker.sql", "CREATE TABLE applied_marker (id INT);\n")
    _backup(env)

    with pytest.raises(SystemExit, match="BEGIN"):
        _apply(env, path)


def test_refuses_without_confirmation(env):
    path = _write(env, "001_marker.sql", MIGRATION)
    _backup(env)

    with pytest.raises(SystemExit, match="--confirm"):
        apply_migration.main(["--file", str(path), "--backup-dir", str(env["backups"]), "--confirm", "yes"])


def test_refuses_files_outside_the_migrations_directory(env, tmp_path):
    stray = tmp_path / "stray.sql"
    stray.write_text(MIGRATION, encoding="utf-8")

    with pytest.raises(SystemExit, match="database/migrations"):
        _apply(env, stray)


def test_applies_the_reviewed_migration_behind_a_verified_backup(env):
    path = _write(env, "001_marker.sql", MIGRATION)
    _backup(env)

    assert _apply(env, path) == 0
    assert _exists(env, "applied_marker")


def test_a_failing_migration_leaves_nothing_behind(env):
    path = _write(env, "002_broken.sql", "BEGIN;\nCREATE TABLE half_done (id INT);\nSELECT 1/0;\nCOMMIT;\n")
    _backup(env)

    assert _apply(env, path) == 1
    assert not _exists(env, "half_done")


def test_a_stale_backup_keeps_the_gate_closed(env):
    path = _write(env, "001_marker.sql", MIGRATION)
    _backup(env)
    manifest_path = next(env["backups"].glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    manifest["created_at"] = "20000101T000000Z"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(SystemExit, match="gate is closed"):
        _apply(env, path)


def test_refuses_a_backup_of_another_database(env, monkeypatch):
    path = _write(env, "001_marker.sql", MIGRATION)
    _backup(env)
    monkeypatch.setenv("DINCR_MIGRATION_DSN", os.environ["OTHER_DSN"])

    with pytest.raises(SystemExit, match="different database"):
        _apply(env, path)


def test_refuses_when_tables_changed_since_the_backup(env):
    path = _write(env, "001_marker.sql", MIGRATION)
    _backup(env)
    conn = psycopg2.connect(env["server"].get_uri(env["target"]))
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE created_after_backup (id INT)")
    conn.close()

    with pytest.raises(SystemExit, match="take a new backup"):
        _apply(env, path)


def test_never_applies_the_same_migration_twice(env):
    path = _write(env, "001_marker.sql", "BEGIN;\nCREATE TABLE IF NOT EXISTS applied_marker (id INT);\nCOMMIT;\n")
    _backup(env)
    assert _apply(env, path) == 0
    env["reset_scratch"]()
    _backup(env)  # the table set changed; a fresh backup is required anyway

    with pytest.raises(SystemExit, match="already applied"):
        _apply(env, path)


@pytest.mark.parametrize("sql, reason", [
    ("BEGIN;\nCREATE TABLE a (id INT);\nCOMMIT;\nSELECT 1;\n", "nothing after COMMIT"),
    ("BEGIN;\nCREATE TABLE a (id INT);\n/*\nCOMMIT;\n*/\n", "nothing after COMMIT"),
    ("BEGIN;\nCREATE TABLE a (id INT);\nCOMMIT;\nBEGIN;\nDROP TABLE a;\nCOMMIT;\n", "not allowed"),
    ("BEGIN;\nSAVEPOINT s;\nCOMMIT;\n", "not allowed"),
    ("-- BEGIN;\nCREATE TABLE a (id INT);\nCOMMIT;\n", "nothing after COMMIT"),
])
def test_only_a_single_transaction_is_accepted(sql, reason):
    with pytest.raises(SystemExit, match=reason):
        apply_migration.check_single_transaction(sql)


def test_the_splitter_ignores_semicolons_and_keywords_in_quotes_and_bodies():
    sql = ("BEGIN;\nCREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $fn$ BEGIN COMMIT; END $fn$;\n"
           "INSERT INTO t VALUES ('a;COMMIT;''b');\n-- COMMIT;\nCOMMIT;\n")
    apply_migration.check_single_transaction(sql)
    assert len(apply_migration.statements(sql)) == 4
