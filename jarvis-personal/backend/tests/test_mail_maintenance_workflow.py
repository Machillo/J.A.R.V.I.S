"""The mail maintenance scheduler (.github/workflows/mail-maintenance.yml) must never look healthy
while reading no mail: an unconfigured scheduled run fails, and a mailbox that could not be read
is surfaced from the backend's counts. The workflow's own result check is executed here."""
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

WORKFLOW = (Path(__file__).resolve().parents[3] / ".github/workflows/mail-maintenance.yml").read_text(encoding="utf-8")


def test_an_unconfigured_scheduled_run_fails_instead_of_a_green_no_op():
    block = re.search(r'if \[ -z "\$BASE_URL" \] \|\| \[ -z "\$CRON_SECRET" \]; then\n(.*?)\n\s*fi\n', WORKFLOW, re.S).group(1)
    assert "exit 1" in block and "exit 0" not in block
    assert "::error::" in block


def result_check() -> str:
    script = re.search(r"python3 - <<'PY'\n(.*?)\n\s*PY\n", WORKFLOW, re.S).group(1)
    return textwrap.dedent(script)


@pytest.mark.parametrize(("body", "exit_code", "annotation"), [
    ({"status": "ok", "connections": 4, "completed": 4, "reconnect": 0, "failed": 0}, 0, None),
    ({"status": "partial", "connections": 4, "completed": 3, "reconnect": 0, "failed": 1}, 0, "::warning::1 connected mailbox(es)"),
    ({"status": "partial", "connections": 2, "completed": 0, "reconnect": 0, "failed": 2}, 1, "::error::No connected mailbox"),
    ({"status": "ok", "connections": 2, "completed": 0, "reconnect": 2, "failed": 0}, 0, None),
])
def test_the_result_check_surfaces_unread_mailboxes(tmp_path, body, exit_code, annotation):
    (tmp_path / "body.json").write_text(json.dumps(body), encoding="utf-8")
    run = subprocess.run([sys.executable, "-c", result_check()], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == exit_code, run.stderr
    if annotation:
        assert annotation in run.stdout
    else:
        assert "::warning::" not in run.stdout and "::error::" not in run.stdout
    # Counts only: the answer never carries a mailbox or account identifier to print.
    assert "@" not in run.stdout
