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
    monkeypatch.setenv("DINCR_MIGRATION_DSN", server.get_uri(target))
    monkeypatch.setenv("SRC_DSN", server.get_uri(target))
    monkeypatch.setenv("SCR_DSN", server.get_uri(scratch))
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    reviewed: dict[str, bytes] = {}
    monkeypatch.setattr(apply_migration, "MIGRATIONS", migrations)
    monkeypatch.setattr(apply_migration, "reviewed_content", lambda path: reviewed.get(path.name, b"<not merged>"))
    yield {"server": server, "target": target, "migrations": migrations, "reviewed": reviewed, "backups": tmp_path / "backups"}
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
