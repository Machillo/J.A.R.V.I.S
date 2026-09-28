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


@pytest.mark.parametrize("script", ["apply_migration", "db_backup_verify"])
def test_an_older_python_stops_with_the_supported_command(script):
    """Run the script as Python 3.9 would see it: the guard stops it before any import."""
    probe = ("import sys, runpy; sys.version_info = (3, 9, 6); "
             f"runpy.run_path({str(ROOT / 'backend' / 'scripts' / (script + '.py'))!r}, run_name='__main__')")
    result = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert f"python3.11 -m backend.scripts.{script}" in result.stderr and "ModuleNotFoundError" not in result.stderr


def test_a_missing_dependency_names_the_supported_setup():
    probe = ("import sys, builtins; real = builtins.__import__\n"
             "def blocked(name, *a, **k):\n"
             "    if name == 'dotenv': raise ModuleNotFoundError(name=name)\n"
             "    return real(name, *a, **k)\n"
             "builtins.__import__ = blocked\nimport backend")
    result = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0 and "Python 3.11" in result.stderr and "python3.11 -m backend.scripts" in result.stderr


def test_the_pinned_runtime_is_python_3_11():
    for pin in (ROOT / "runtime.txt", ROOT / ".python-version"):
        assert "3.11" in pin.read_text(encoding="utf-8")
