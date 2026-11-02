"""The IBKR daily sync scheduler (.github/workflows/ibkr-sync.yml) calls the existing read-only Flex
endpoint with its own secret header, never looks healthy while syncing nothing, and logs no account
identifier or amount. The workflow's own result check is executed here."""
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[3] / ".github/workflows/ibkr-sync.yml").read_text(encoding="utf-8")
ROUTER = (Path(__file__).resolve().parents[1] / "integrations/ibkr_readonly.py").read_text(encoding="utf-8")


def test_it_calls_the_flex_cron_endpoint_with_the_header_the_backend_reads():
    assert '"${BASE_URL%/}/integrations/ibkr/flex/cron"' in WORKFLOW
    assert '@router.post("/flex/cron")' in ROUTER and "x_jarvis_cron_secret" in ROUTER   # FastAPI: X-Jarvis-Cron-Secret
    assert '-H "X-Jarvis-Cron-Secret: ${CRON_SECRET}"' in WORKFLOW


def test_an_unconfigured_scheduled_run_fails_instead_of_a_green_no_op():
    block = re.search(r'if \[ -z "\$BASE_URL" \] \|\| \[ -z "\$CRON_SECRET" \]; then\n(.*?)\n\s*fi\n', WORKFLOW, re.S).group(1)
    assert "exit 1" in block and "exit 0" not in block and "::error::" in block
    result = WORKFLOW.split('case "$code" in')[2]   # the answer's case, after the retry loop's
    for code in ("403|503)", "502)", "*)"):
        branch = result.split(code, 1)[1].split(";;", 1)[0]
        assert "exit 1" in branch, code


def test_the_result_check_logs_only_a_status_a_date_and_a_count(tmp_path):
    script = textwrap.dedent(re.search(r"python3 - <<'PY'\n(.*?)\n\s*PY\n", WORKFLOW, re.S).group(1))
    body = {"status": "OK", "snapshot_id": 12, "captured_at": "2026-11-02T21:00:00+00:00", "positions": 2,
            "account_id": "U1234567", "net_liquidation": 15234.55}
    (tmp_path / "body.json").write_text(json.dumps(body), encoding="utf-8")
    run = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "2026-11-02" in run.stdout and "'positions': 2" in run.stdout
    assert "U1234567" not in run.stdout and "15234" not in run.stdout
