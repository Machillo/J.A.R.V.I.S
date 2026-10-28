"""What the Native apps workflow (.github/workflows/native-ci.yml) runs for a change.

Two decisions, both deterministic:

1. **Which platforms a pull request touches** (``plan``). The iOS XCUITest suite is the slow
   part of CI (about 50 minutes in one simulator). A pull request that changes only the
   backend's view of the reachability spec, or only Android, does not need it:
   - ``ios``: anything under ``jarvis-personal/native/`` except Android and the spec file, plus
     DESIGN.md (token source), the workflow and this script;
   - ``android``: anything under ``jarvis-personal/native/`` except iOS and the spec file, plus
     DESIGN.md, the workflow and this script;
   - ``spec``: ``jarvis-personal/native/feature-reachability.json``. Both apps read it, so a
     spec-only change runs the fast suites and the iOS reachability flows, not the whole UI suite.
   A push to ``main`` runs everything.

2. **How the iOS UI suite is split** (``shard``). Test classes are found in
   ``DINCRUITests/*.swift`` and placed on N runners by their measured duration (longest first,
   onto the least loaded runner). A class without a measurement weighs DEFAULT_SECONDS, so a
   new test file is always run by exactly one shard. Every runner computes the same split.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

NATIVE = "jarvis-personal/native/"
SPEC = NATIVE + "feature-reachability.json"
UI_TESTS = Path("jarvis-personal/native/ios/DINCRUITests")
UI_TARGET = "DINCRUITests"
SPEC_UI_CLASSES = ("FeatureReachabilityUITests",)
SHARED = ("DESIGN.md", ".github/workflows/native-ci.yml", ".github/scripts/native_ci_plan.py")
DEFAULT_SECONDS = 60
# Seconds per class on a passing CI run (2026-10-28). Only the balance depends on them.
MEASURED_SECONDS = {
    "FeatureReachabilityUITests": 452, "PlanAccountsUITests": 335, "OwnerExperienceUITests": 238,
    "PullToRefreshUITests": 219, "DINCRUITests": 208, "PlanOrganizeUITests": 148,
    "OwnerInformationClarityUITests": 140, "JarvisChatUITests": 131, "SummaryChartsUITests": 101,
    "ProjectionsUITests": 99, "MoneyControlUITests": 91, "AttentionUITests": 81, "LockedRowsUITests": 65,
    "NavigationUITests": 65, "HomeTodayUITests": 64, "MoneyUITests": 56, "JarvisAccessUITests": 53,
    "OwnerWealthUITests": 52, "OwnerAnalysisPlacementUITests": 43, "WealthUITests": 42,
    "JarvisAgendaUITests": 38, "MovementsReviewUITests": 36, "DebtScenarioUITests": 35,
    "MailOnReturnUITests": 33, "DebtPayoffUITests": 33, "RecordsUITests": 32, "PublicScoreUITests": 30,
    "OwnAccountsUITests": 28, "StoreSubscriptionUITests": 28, "PlainLanguageUITests": 25,
    "PendingConversionUITests": 24, "DebtPaymentsUITests": 24, "PaidWithUITests": 23, "LegalGateUITests": 22,
    "KeepContentUITests": 17, "ClosePeriodUITests": 17, "SavingsPlanEditUITests": 15, "QuickActionUITests": 11,
    "StoreScreenshots": 1,
}
CLASS = re.compile(r"^\s*(?:final\s+)?class\s+(\w+)\s*:\s*XCTestCase\b", re.MULTILINE)


def plan(changed: list[str], *, full: bool) -> dict[str, bool]:
    if full:
        return {"ios": True, "android": True, "spec": True}
    ios = android = spec = False
    for path in changed:
        if path in SHARED:
            ios = android = True
        elif path == SPEC:
            spec = True
        elif path.startswith(NATIVE + "ios/"):
            ios = True
        elif path.startswith(NATIVE + "android/"):
            android = True
        elif path.startswith(NATIVE):
            ios = android = True
    return {"ios": ios, "android": android, "spec": spec}


def ui_classes(root: Path = UI_TESTS) -> list[str]:
    found = {name for file in sorted(root.glob("*.swift")) for name in CLASS.findall(file.read_text(encoding="utf-8"))}
    return sorted(found)


def shard(classes: list[str], count: int) -> list[list[str]]:
    """Longest-first onto the least loaded runner; ties by name, so every runner agrees."""
    loads = [[0, index, []] for index in range(count)]
    for name in sorted(classes, key=lambda c: (-MEASURED_SECONDS.get(c, DEFAULT_SECONDS), c)):
        target = min(loads, key=lambda load: (load[0], load[1]))
        target[0] += MEASURED_SECONDS.get(name, DEFAULT_SECONDS)
        target[2].append(name)
    return [sorted(load[2]) for load in loads]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="print ios/android/spec as GitHub outputs")
    p.add_argument("--full", action="store_true")
    p.add_argument("--changed-file", type=Path)
    s = sub.add_parser("shard", help="print the -only-testing arguments of one runner")
    s.add_argument("--count", type=int, required=True)
    s.add_argument("--index", required=True, help="1..count, or 'spec' for the reachability flows only")
    args = parser.parse_args(argv)
    if args.command == "plan":
        changed = args.changed_file.read_text(encoding="utf-8").split() if args.changed_file else []
        result = plan(changed, full=args.full)
        print("\n".join(f"{key}={str(value).lower()}" for key, value in result.items()))
        return 0
    if args.index == "spec":
        selected = list(SPEC_UI_CLASSES)
    else:
        selected = shard(ui_classes(), args.count)[int(args.index) - 1]
    if not selected:
        print("no UI test classes for this shard", file=sys.stderr)
        return 1
    print(" ".join(f"-only-testing:{UI_TARGET}/{name}" for name in selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
