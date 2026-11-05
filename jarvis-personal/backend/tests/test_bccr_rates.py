"""The dollar's rate: what is read from each answer, which service wins, which rate a
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


def today_answer(day="2026-11-04", value=454.65):
    return {"venta": {"fecha": day, "valor": value}, "compra": {"fecha": day, "valor": 450.31}}


def history_row(day, rate, quote="CRC"):
    return {"date": day, "base": "USD", "quote": quote, "rate": rate}


def test_today_reads_the_selling_rate_never_the_buying_one():
    assert br.parse_today(today_answer()) == [(date(2026, 11, 4), Decimal("454.65"))]


def test_history_reads_dollars_in_colones_only():
    rows = br.parse_history([history_row("2026-11-03", 455.1), history_row("2026-11-03", 0.9, quote="EUR"), history_row("2026-11-04", None)])
    assert rows == [(date(2026, 11, 3), Decimal("455.1"))]


@pytest.mark.parametrize("value", [0, -5, 1, 99999, "abc", True, float("inf"), [], {}, None])
def test_a_value_that_cannot_be_this_rate_is_never_stored(value):
    assert br.parse_today(today_answer(value=value)) == []
    assert br.parse_history([history_row("2026-11-02", value)]) == []


@pytest.mark.parametrize("payload", [None, [], {}, {"compra": {"fecha": "2026-11-04", "valor": 450}}, {"code": 503, "status": "Service unavailable"}])
def test_a_refused_answer_from_hacienda_raises(payload):
    with pytest.raises(br.RateFeedError):
        br.parse_today(payload)


@pytest.mark.parametrize("payload", [None, {}, {"message": "not found"}])
def test_a_refused_answer_from_the_history_raises(payload):
    with pytest.raises(br.RateFeedError):
        br.parse_history(payload)


class Response:
    def __init__(self, status, body=None):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


def test_only_a_date_range_goes_out_with_no_credential(monkeypatch):
    seen = {}

    def get(url, params, headers, timeout):
        seen.update(url=url, params=params, headers=headers)
        return Response(200, [history_row("2026-11-02", 512)])

    monkeypatch.setattr(br.requests, "get", get)
    assert br.fetch_history(date(2026, 11, 1), date(2026, 11, 2)) == [(date(2026, 11, 2), Decimal("512"))]
    assert seen["params"] == {"from": "2026-11-01", "to": "2026-11-02", "base": "USD", "quotes": "CRC", "providers": "BCCR"}
    assert "Authorization" not in seen["headers"]


def test_an_error_answer_raises(monkeypatch):
    monkeypatch.setattr(br.requests, "get", lambda *a, **k: Response(503))
    with pytest.raises(br.RateFeedError):
        br.fetch_today()


class FakeConn:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.log.append(params)

    def commit(self):
        pass


@pytest.fixture
def cron(monkeypatch):
    from backend.user_product import pending_conversion

    log = []
    monkeypatch.setenv("EMAIL_MONITOR_CRON_SECRET", "synthetic")
    monkeypatch.delenv("IBKR_FLEX_CRON_SECRET", raising=False)
    monkeypatch.setattr(br, "get_connection", lambda: FakeConn(log))
    monkeypatch.setattr(br, "costa_rica_today", lambda: date(2026, 11, 4))
    monkeypatch.setattr(br.observability, "heartbeat", lambda *a, **k: None)
    monkeypatch.setattr(pending_conversion, "close_due_periods", lambda today: {"converted": 1})
    return log


def test_todays_official_rate_is_stored_last_so_it_wins_on_its_day(cron, monkeypatch):
    day = date(2026, 11, 4)
    monkeypatch.setattr(br, "fetch_history", lambda *_: [(day, Decimal("450"))])
    monkeypatch.setattr(br, "fetch_today", lambda: [(day, Decimal("454.65"))])
    answer = br.sync_rates_cron("synthetic")
    assert [row[-1] for row in cron] == [br.SOURCE_HISTORY, br.SOURCE_TODAY]
    assert answer["rates"] == 1 and answer["failed_sources"] == 0 and answer["converted"] == 1


def test_history_never_replaces_a_day_hacienda_published():
    class Connection:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params):
            self.calls.append((sql, params))

    conn = Connection()
    br.store(conn, [(date(2026, 11, 3), Decimal("455.1"))], br.SOURCE_HISTORY)
    sql, params = conn.calls[0]
    assert "WHERE market_exchange_rates.source <> 'hacienda' OR EXCLUDED.source = 'hacienda'" in sql
    assert params[-1] == br.SOURCE_HISTORY


def test_one_service_down_does_not_stop_the_other(cron, monkeypatch):
    def down(*_):
        raise br.RateFeedError("HTTP 503")

    monkeypatch.setattr(br, "fetch_history", down)
    monkeypatch.setattr(br, "fetch_today", lambda: [(date(2026, 11, 4), Decimal("454.65"))])
    assert br.sync_rates_cron("synthetic")["failed_sources"] == 1
    assert len(cron) == 1


def test_both_down_still_closes_with_what_is_stored_and_fails_loudly(cron, monkeypatch):
    from backend.user_product import pending_conversion

    def down(*_):
        raise br.RateFeedError("HTTP 503")

    called = []
    monkeypatch.setattr(pending_conversion, "close_due_periods", lambda today: called.append(today) or {})
    monkeypatch.setattr(br, "fetch_history", down)
    monkeypatch.setattr(br, "fetch_today", down)
    with pytest.raises(HTTPException) as failed:
        br.sync_rates_cron("synthetic")
    assert failed.value.status_code == 502 and called == [date(2026, 11, 4)] and cron == []


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
            "waiting_for_rate": 0, "failed_workspaces": 0, "failed_sources": 0, "workspace_id": "SECRET-WS", "amount": 98765}
    (tmp_path / "body.json").write_text(json.dumps(body), encoding="utf-8")
    run = subprocess.run([sys.executable, "-c", _result_check()], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "2026-11-04" in run.stdout and "'converted': 3" in run.stdout
    assert "SECRET-WS" not in run.stdout and "98765" not in run.stdout


def test_a_workspace_that_failed_makes_the_run_fail(tmp_path):
    (tmp_path / "body.json").write_text(json.dumps({"status": "OK", "failed_workspaces": 1}), encoding="utf-8")
    run = subprocess.run([sys.executable, "-c", _result_check()], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode != 0
