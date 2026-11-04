"""The Banco Central's dollar rate: what is read from an answer, how the token travels, which rate a
close uses, the cron's credential, and the scheduler. Invented figures, no network."""
import json
import re
import subprocess
import sys
import textwrap
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.integrations import bccr_rates as br

WORKFLOW = (Path(__file__).resolve().parents[3] / ".github/workflows/exchange-rate-sync.yml").read_text(encoding="utf-8")


def answer(*series, code="318", estado=True):
    return {"estado": estado, "mensaje": "ok", "datos": [{"codigoIndicador": code, "series": list(series)}]}


def serie(day, value):
    return {"fecha": day, "valorDatoPorPeriodo": value}


def test_it_reads_the_days_with_a_value_and_leaves_the_others_unknown():
    rows = br.parse_series(answer(serie("2026-11-02", 512.34), serie("2026-11-03T00:00:00", "513.5"), serie("2026-11-04", None)))
    assert rows == [(date(2026, 11, 2), Decimal("512.34")), (date(2026, 11, 3), Decimal("513.5"))]


@pytest.mark.parametrize("value", [0, -5, 1, 99999, "abc", True, float("inf"), [], {}])
def test_a_value_that_cannot_be_this_rate_is_never_stored(value):
    assert br.parse_series(answer(serie("2026-11-02", value))) == []


@pytest.mark.parametrize("payload", [None, [], {}, {"estado": False, "datos": []}, {"estado": True}, answer(serie("2026-11-02", 500), code="317")])
def test_a_refused_or_foreign_answer_raises(payload):
    with pytest.raises(br.RateFeedError):
        br.parse_series(payload)


class Response:
    def __init__(self, status, body=None):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


def test_the_token_goes_in_the_header_and_the_range_is_all_that_goes_out(monkeypatch):
    seen = {}

    def get(url, params, headers, timeout):
        seen.update(url=url, params=params, headers=headers)
        return Response(200, answer(serie("2026-11-02", 512)))

    monkeypatch.setenv(br.TOKEN_ENV, "synthetic-token")
    monkeypatch.setattr(br.requests, "get", get)
    assert br.fetch_series(date(2026, 11, 1), date(2026, 11, 2)) == [(date(2026, 11, 2), Decimal("512"))]
    assert seen["headers"]["Authorization"] == "Bearer synthetic-token"
    assert "synthetic-token" not in seen["url"] and "synthetic-token" not in json.dumps(seen["params"])
    assert seen["params"] == {"fechaInicio": "2026/11/01", "fechaFin": "2026/11/02", "idioma": "ES"}
    assert "/indicadoresEconomicos/318/series" in seen["url"]


def test_without_a_token_nothing_is_requested(monkeypatch):
    monkeypatch.delenv(br.TOKEN_ENV, raising=False)
    monkeypatch.setattr(br.requests, "get", lambda *a, **k: pytest.fail("no request without a token"))
    with pytest.raises(br.RateFeedError):
        br.fetch_series(date(2026, 11, 1), date(2026, 11, 2))


def test_an_error_answer_never_carries_the_token(monkeypatch):
    monkeypatch.setenv(br.TOKEN_ENV, "synthetic-token")
    monkeypatch.setattr(br.requests, "get", lambda *a, **k: Response(401))
    with pytest.raises(br.RateFeedError) as error:
        br.fetch_series(date(2026, 11, 1), date(2026, 11, 2))
    assert "synthetic-token" not in str(error.value)


RATES = {date(2026, 11, 2): Decimal("510"), date(2026, 11, 5): Decimal("515")}


def test_a_day_without_a_rate_uses_the_closest_earlier_one_and_only_for_a_week():
    assert br.rate_on_or_before(RATES, date(2026, 11, 2)) == Decimal("510")
    assert br.rate_on_or_before(RATES, date(2026, 11, 4)) == Decimal("510")
    assert br.rate_on_or_before(RATES, date(2026, 11, 12)) == Decimal("515")
    assert br.rate_on_or_before(RATES, date(2026, 11, 13)) is None
    assert br.rate_on_or_before(RATES, date(2026, 11, 1)) is None


def test_a_close_uses_the_rate_of_its_last_day():
    assert br.closing_rate(RATES, date(2026, 11, 5), today=date(2026, 11, 9)) == Decimal("515")


def test_on_the_cut_day_itself_the_close_waits_for_that_days_rate():
    assert br.closing_rate(RATES, date(2026, 11, 4), today=date(2026, 11, 4)) is None
    assert br.closing_rate(RATES, date(2026, 11, 5), today=date(2026, 11, 5)) == Decimal("515")


def test_the_next_day_it_falls_back_to_the_last_published_rate():
    assert br.closing_rate(RATES, date(2026, 11, 4), today=date(2026, 11, 5)) == Decimal("510")


def test_the_cron_refuses_a_wrong_or_missing_credential(monkeypatch):
    monkeypatch.delenv("IBKR_FLEX_CRON_SECRET", raising=False)
    monkeypatch.setenv("EMAIL_MONITOR_CRON_SECRET", "synthetic")
    for secret in (None, "other"):
        with pytest.raises(HTTPException) as refused:
            br.sync_rates_cron(secret)
        assert refused.value.status_code == 403
    monkeypatch.delenv("EMAIL_MONITOR_CRON_SECRET")
    with pytest.raises(HTTPException) as refused:
        br.sync_rates_cron("synthetic")
    assert refused.value.status_code == 503


def test_the_workflow_calls_the_cron_and_never_looks_healthy_without_settings():
    assert '"${BASE_URL%/}/integrations/exchange-rates/cron"' in WORKFLOW
    assert '-H "X-Jarvis-Cron-Secret: ${CRON_SECRET}"' in WORKFLOW
    block = re.search(r'if \[ -z "\$BASE_URL" \] \|\| \[ -z "\$CRON_SECRET" \]; then\n(.*?)\n\s*fi\n', WORKFLOW, re.S).group(1)
    assert "exit 1" in block and "exit 0" not in block
    result = WORKFLOW.split('case "$code" in')[2]
    for code in ("403|503)", "502)", "*)"):
        assert "exit 1" in result.split(code, 1)[1].split(";;", 1)[0], code


def _result_check():
    return textwrap.dedent(re.search(r"python3 - <<'PY'\n(.*?)\n\s*PY\n", WORKFLOW, re.S).group(1))


def test_the_result_check_logs_only_a_status_a_date_and_counts(tmp_path):
    body = {"status": "OK", "latest_rate_date": "2026-11-04", "rates": 45, "closed_periods": 1, "converted": 3,
            "waiting_for_rate": 0, "failed_workspaces": 0, "workspace_id": "SECRET-WS", "amount": 98765}
    (tmp_path / "body.json").write_text(json.dumps(body), encoding="utf-8")
    run = subprocess.run([sys.executable, "-c", _result_check()], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "2026-11-04" in run.stdout and "'converted': 3" in run.stdout
    assert "SECRET-WS" not in run.stdout and "98765" not in run.stdout


def test_a_workspace_that_failed_makes_the_run_fail(tmp_path):
    (tmp_path / "body.json").write_text(json.dumps({"status": "OK", "failed_workspaces": 1}), encoding="utf-8")
    run = subprocess.run([sys.executable, "-c", _result_check()], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode != 0
