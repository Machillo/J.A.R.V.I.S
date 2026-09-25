"""The migration tooling runs the way the protocol documents it (#247 follow-up)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # jarvis-personal/


@pytest.mark.parametrize("script", ["apply_migration", "db_backup_verify"])
@pytest.mark.parametrize("form", ["module", "file"])
def test_both_invocations_reach_the_argument_parser(script, form):
    command = [sys.executable, "-m", f"backend.scripts.{script}", "--help"] if form == "module" else \
        [sys.executable, str(ROOT / "backend" / "scripts" / f"{script}.py"), "--help"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-400:]
    assert "usage:" in result.stdout


def test_an_older_python_gets_a_clear_message_not_an_import_error():
    source = (ROOT / "backend" / "scripts" / "apply_migration.py").read_text(encoding="utf-8")
    guard = source.index("sys.version_info < (3, 11)")
    assert guard < source.index("import psycopg2") and guard < source.index("from backend.scripts import")
    assert "python3.11 -m backend.scripts.apply_migration" in source
    init = (ROOT / "backend" / "__init__.py").read_text(encoding="utf-8")
    assert init.index("sys.version_info < (3, 11)") < init.index("from backend.core.env import")
    assert (ROOT / "runtime.txt").read_text().strip().startswith("python-3.11")
