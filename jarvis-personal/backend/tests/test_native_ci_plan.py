"""Unit tests for the Native apps CI plan (.github/scripts/native_ci_plan.py).

The plan decides which platforms a pull request runs and splits the iOS UI suite across
runners. Running too little is the dangerous direction, so the tests pin that every native
change runs its platform and that every UI test class lands on exactly one runner.
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("native_ci_plan", REPO / ".github" / "scripts" / "native_ci_plan.py")
ci = importlib.util.module_from_spec(_spec)
sys.modules["native_ci_plan"] = ci
_spec.loader.exec_module(ci)


def test_a_backend_only_change_runs_no_native_platform():
    assert ci.plan(["jarvis-personal/backend/finance/routes.py"], full=False) == {"ios": False, "android": False, "spec": False}


def test_a_spec_only_change_runs_the_spec_checks_not_the_whole_ios_suite():
    assert ci.plan([ci.SPEC, "jarvis-personal/backend/tests/fixtures/route_gate_inventory.json"], full=False) == \
        {"ios": False, "android": False, "spec": True}


def test_each_platform_runs_for_its_own_files():
    assert ci.plan(["jarvis-personal/native/ios/DINCR/App/QuickActions.swift"], full=False) == {"ios": True, "android": False, "spec": False}
    assert ci.plan(["jarvis-personal/native/android/app/build.gradle.kts"], full=False) == {"ios": False, "android": True, "spec": False}


def test_shared_native_files_the_workflow_and_this_script_run_both_platforms():
    for path in ("DESIGN.md", ".github/workflows/native-ci.yml", ".github/scripts/native_ci_plan.py",
                 "jarvis-personal/native/design-tokens/generate.mjs"):
        assert ci.plan([path], full=False) == {"ios": True, "android": True, "spec": False}, path


def test_main_runs_everything():
    assert ci.plan([], full=True) == {"ios": True, "android": True, "spec": True}


def test_every_ui_test_class_runs_on_exactly_one_runner_and_the_split_is_balanced():
    classes = ci.ui_classes(REPO / ci.UI_TESTS)
    assert "FeatureReachabilityUITests" in classes and len(classes) >= 30
    shards = ci.shard(classes, 4)
    flat = [name for shard in shards for name in shard]
    assert sorted(flat) == sorted(classes) and len(flat) == len(set(flat))
    loads = [sum(ci.MEASURED_SECONDS.get(name, ci.DEFAULT_SECONDS) for name in shard) for shard in shards]
    assert max(loads) - min(loads) <= max(ci.MEASURED_SECONDS.values())
    assert ci.shard(classes, 4) == shards, "every runner computes the same split"


def test_a_new_test_file_is_run_by_one_runner(tmp_path):
    (tmp_path / "A.swift").write_text("final class AlphaUITests: XCTestCase {}\nclass Helper {}\n")
    (tmp_path / "B.swift").write_text("class BetaUITests: XCTestCase {\n}\n")
    classes = ci.ui_classes(tmp_path)
    assert classes == ["AlphaUITests", "BetaUITests"]
    assert sorted(name for shard in ci.shard(classes, 4) for name in shard) == classes


def test_the_shard_arguments_name_the_test_target(capsys):
    assert ci.main(["shard", "--count", "4", "--index", "spec"]) == 0
    assert capsys.readouterr().out.strip() == "-only-testing:DINCRUITests/FeatureReachabilityUITests"
