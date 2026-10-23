"""The financial-history workflow's result check (.github/scripts/financial_history_result.py)."""
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("financial_history_result", REPO / ".github" / "scripts" / "financial_history_result.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

OK = {"status": "OK", "date": "2026-10-20", "eligible": 7, "recorded": 7, "strategy_changed": 1, "failed": 0,
      "debt_installments": 7, "installments_failed": 0, "installments_errors": []}


def test_a_clean_run_passes_and_logs_its_counts():
    lines, code = check.evaluate(OK)
    assert code == 0
    assert "'debt_installments': 7" in lines[0] and "'installments_failed': 0" in lines[0]
    assert not any(line.startswith("::error::") for line in lines)


def test_a_failed_installment_step_fails_the_check_with_its_error_class():
    lines, code = check.evaluate({**OK, "debt_installments": 0, "installments_failed": 1, "installments_errors": ["OperationalError"]})
    assert code == 1
    assert any(line.startswith("::error::") and "OperationalError" in line for line in lines)


def test_a_failed_workspace_fails_the_check():
    lines, code = check.evaluate({**OK, "recorded": 6, "failed": 1})
    assert code == 1 and any("1 workspace(s) failed" in line for line in lines)


@pytest.mark.parametrize("status", ["ALREADY_RUNNING", None, "ERROR"])
def test_an_unexpected_status_fails_the_check(status):
    assert check.evaluate({**OK, "status": status})[1] == 1


@pytest.mark.parametrize("value", ["two", None, [], {"x": 1}])
def test_an_unreadable_failure_count_is_a_failure_never_a_zero(value):
    if value is None:  # an explicit null means none failed
        assert check.evaluate({**OK, "installments_failed": value})[1] == 0
    else:
        assert check.evaluate({**OK, "installments_failed": value})[1] == 1


def test_error_text_that_is_not_a_class_name_is_never_logged():
    lines, code = check.evaluate({**OK, "installments_failed": 1,
                                  "installments_errors": ["RuntimeError", "debt 22 balance 401853.00", "<script>"]})
    joined = "\n".join(lines)
    assert code == 1 and "RuntimeError" in joined
    assert "401853" not in joined and "<script>" not in joined


def test_a_backend_without_the_installment_step_warns_without_failing():
    older = {key: value for key, value in OK.items() if not key.startswith(("debt_", "installments_"))}
    lines, code = check.evaluate(older)
    assert code == 0 and any(line.startswith("::warning::") for line in lines)


def test_main_reads_the_body_and_rejects_what_is_not_a_result(tmp_path, capsys):
    body = tmp_path / "body.json"
    body.write_text(json.dumps({**OK, "installments_failed": 1, "installments_errors": ["RuntimeError"]}), encoding="utf-8")
    assert check.main(["x", str(body)]) == 1
    assert "RuntimeError" in capsys.readouterr().out
    body.write_text("not json", encoding="utf-8")
    assert check.main(["x", str(body)]) == 1
    body.write_text("[1, 2]", encoding="utf-8")
    assert check.main(["x", str(body)]) == 1
    assert check.main(["x"]) == 1


def test_the_workflow_runs_the_check_and_checks_out_only_the_scripts():
    workflow = (REPO / ".github" / "workflows" / "financial-history.yml").read_text(encoding="utf-8")
    assert "python3 .github/scripts/financial_history_result.py body.json" in workflow
    assert "sparse-checkout: .github/scripts" in workflow and "persist-credentials: false" in workflow
