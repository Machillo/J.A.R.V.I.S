"""Run code in a fresh Labs child process (the only place Labs may activate)."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from labs.__main__ import _child_env

ROOT = Path(__file__).resolve().parents[2]


def run_child(code: str, dsn: str, *, extra_env: dict[str, str] | None = None, timeout: int = 240) -> dict:
    """Run `code` (which must print one JSON line last) in a scrubbed Labs child; return that JSON."""
    env = {**_child_env(dsn), **(extra_env or {})}
    completed = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], env=env, cwd=str(ROOT),
                               capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False)
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0 or not lines:
        raise AssertionError(f"child failed ({completed.returncode}):\n{completed.stdout[-2000:]}\n{completed.stderr[-4000:]}")
    return json.loads(lines[-1])
