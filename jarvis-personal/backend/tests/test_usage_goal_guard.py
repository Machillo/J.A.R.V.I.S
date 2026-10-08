"""UX-1 guard: the onboarding answer `usage_goal` never shapes DINCR's money decisions.

The profile-setup question "¿Qué querés lograr primero?" (`accounts.usage_goal`) is kept only to
personalize presentation. No engine may read it to change a figure, a priority, a recommendation, a
budget or a strategy.

Two guards:
- Static: only the identity/profile code may name the field, and there only in the functions that
  store it (profile setup) and return it with the identity (`enrich_identity`). A new reader
  anywhere else fails here and must be reviewed.
- Behavioural: the same synthetic account, run through the VIP command center, the VIP strategy and
  the declared situation, gives exactly the same results whatever goal it chose, or none (the
  identity carries `usage_goal`, as `enrich_identity` puts it there).

All data is synthetic.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.core.i18n import use_language
from backend.user_product import service, vip_service
from backend.user_product.test_mail_preserves_financial_state import ACCOUNT, ALLOWED_USER_ID, WORKSPACE, db  # noqa: F401 (fixture)

BACKEND = Path(__file__).resolve().parents[1]
FIELD = "usage_goal"
GOALS = ("debt", "save", "partner", "life_change", "control", "explore")

# The only places allowed to name the field, and why.
ALLOWED_FILES = {
    "auth/models.py": "the profile-setup request validates the answer",
    "auth/saas.py": "profile setup stores it; the identity returns it to the apps",
}
ALLOWED_FUNCTIONS_IN_SAAS = {"enrich_identity", "complete_profile_setup"}


def _production_sources():
    for path in sorted(BACKEND.rglob("*.py")):
        relative = path.relative_to(BACKEND).as_posix()
        name = path.name
        if relative.startswith("tests/") or name.startswith("test_") or name == "conftest.py":
            continue
        yield relative, path


def test_only_the_profile_code_names_usage_goal():
    readers = sorted(relative for relative, path in _production_sources()
                     if FIELD in path.read_text(encoding="utf-8") and relative not in ALLOWED_FILES)
    assert readers == [], (
        f"{FIELD} is a personalization answer and must not reach financial code; new readers: {readers}. "
        "If one is legitimate (presentation only), review it and add it to ALLOWED_FILES with the reason."
    )


def test_the_profile_code_reads_it_only_to_store_and_return_it():
    source = (BACKEND / "auth/saas.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    lines_with_field = {number for number, line in enumerate(source.splitlines(), start=1) if FIELD in line}
    owners = set()
    for number in lines_with_field:
        enclosing = [f for f in functions if f.lineno <= number <= (f.end_lineno or f.lineno)]
        owners.add(min(enclosing, key=lambda f: (f.end_lineno or f.lineno) - f.lineno).name if enclosing else "<module>")
    assert lines_with_field, "the identity no longer returns usage_goal; update this guard"
    assert owners <= ALLOWED_FUNCTIONS_IN_SAAS, f"{FIELD} read outside profile setup / identity: {sorted(owners - ALLOWED_FUNCTIONS_IN_SAAS)}"


def _decisions(goal):
    identity = {"id": ALLOWED_USER_ID, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": "user", FIELD: goal}
    token = set_current_user(identity)
    try:
        with use_language("es"):
            center = vip_service.get_vip_command_center()
            center.pop("as_of", None)
            return json.dumps({
                "command_center": center,
                "strategy_vip": service.get_strategy_vip(),
                "situation": service.get_financial_situation(),
            }, sort_keys=True, default=str)
    finally:
        reset_current_user(token)


@pytest.mark.parametrize("goal", GOALS)
def test_the_chosen_goal_never_changes_a_financial_result(db, goal):  # noqa: F811 (fixture)
    baseline = _decisions(None)
    assert '"priority"' in baseline  # the engines really ran
    assert _decisions(goal) == baseline, f"usage_goal={goal!r} changed a financial result"
