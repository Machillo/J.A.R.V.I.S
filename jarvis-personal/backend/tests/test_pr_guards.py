"""Unit tests for the PR guards (.github/scripts/pr_guards.py)."""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("pr_guards", REPO / ".github" / "scripts" / "pr_guards.py")
guards = importlib.util.module_from_spec(_spec)
sys.modules["pr_guards"] = guards  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(guards)

BUDGET_SOURCE = '''
ROOT = Path(__file__).resolve().parents[2]
BUDGETS = {
    ROOT / "backend/finance/service.py": %d,
    ROOT / "frontend/src/pages/Finance.jsx": %d,
}
'''


def result():
    return guards.Result()


def test_a_pr_based_on_another_branch_fails_unless_explicitly_authorized():
    stacked = result()
    guards.check_base("feat/other-work", set(), stacked)
    assert stacked.errors and "not 'main'" in stacked.errors[0]

    authorized = result()
    guards.check_base("feat/other-work", {guards.LABEL_STACKED}, authorized)
    assert not authorized.errors and authorized.warnings

    normal = result()
    guards.check_base("main", set(), normal)
    assert not normal.errors and not normal.warnings


def test_hidden_stacking_on_another_open_pr_is_detected():
    open_prs = [{"number": 10, "headRefOid": "a" * 40}, {"number": 11, "headRefOid": "b" * 40}]
    stacked = result()
    guards.check_hidden_stacking({"a" * 40, "c" * 40}, open_prs, own_number=11, labels=set(), result=stacked)
    assert stacked.errors and "#10" in stacked.errors[0]

    independent = result()
    guards.check_hidden_stacking({"c" * 40}, open_prs, own_number=11, labels=set(), result=independent)
    assert not independent.errors

    own_head_is_not_stacking = result()
    guards.check_hidden_stacking({"b" * 40}, open_prs, own_number=11, labels=set(), result=own_head_is_not_stacking)
    assert not own_head_is_not_stacking.errors


def test_a_merge_into_a_branch_other_than_main_is_flagged():
    lost = result()
    guards.check_merged_target("closed", True, "fix/already-merged-base", lost)
    assert lost.errors and "NOT in 'main'" in lost.errors[0]

    for action, merged, base in (("closed", True, "main"), ("closed", False, "feature"), ("synchronize", False, "feature")):
        fine = result()
        guards.check_merged_target(action, merged, base, fine)
        assert not fine.errors


def test_budgets_may_decrease_but_not_rise_or_disappear():
    base = BUDGET_SOURCE % (3060, 1510)
    assert guards.parse_budgets(base) == {"backend/finance/service.py": 3060, "frontend/src/pages/Finance.jsx": 1510}

    lowered = result()
    guards.check_budgets(base, BUDGET_SOURCE % (3000, 1510), set(), lowered)
    assert not lowered.errors

    raised = result()
    guards.check_budgets(base, BUDGET_SOURCE % (3061, 1510), set(), raised)
    assert raised.errors and "3060 -> 3061" in raised.errors[0]

    removed = result()
    guards.check_budgets(base, 'BUDGETS = {ROOT / "backend/finance/service.py": 3060}', set(), removed)
    assert removed.errors and "removed" in removed.errors[0]

    approved = result()
    guards.check_budgets(base, BUDGET_SOURCE % (3061, 1510), {guards.LABEL_BUDGET}, approved)
    assert not approved.errors and approved.warnings


def test_the_real_budget_script_is_parseable():
    source = (REPO / guards.BUDGET_SCRIPT).read_text(encoding="utf-8")
    budgets = guards.parse_budgets(source)
    assert budgets and all(isinstance(limit, int) and limit > 0 for limit in budgets.values())


@pytest.mark.parametrize("labels, blocked", [(set(), True), ({"migration-gate-acknowledged"}, False)])
def test_a_new_migration_is_a_visible_human_gate(labels, blocked):
    gate = result()
    guards.check_migrations(["jarvis-personal/database/migrations/20990101000000_example.sql", "README.md"], labels, gate)
    assert bool(gate.errors) is blocked
    assert "PRE-MERGE GATE" in (gate.errors or gate.notes)[0]

    none = result()
    guards.check_migrations(["jarvis-personal/backend/main.py"], set(), none)
    assert not none.errors and not none.notes
