"""Pull-request guards for DINCR (run by .github/workflows/pr-guards.yml).

They catch classes of errors that already happened:
- a PR whose base is not ``main``: a stacked PR can show MERGED while its
  commits never reach ``main``;
- a PR whose commits contain another open PR's head (hidden stacking);
- a PR merged into a branch other than ``main``;
- a file-size budget raised to let the same file pass;
- a new database migration, which is a deployment gate: merging to main can
  deploy the backend before production has the schema.

Each error has an explicit override label that a human sets on purpose. The
guards cannot know production state: the migration label is a human
attestation, not a check that the migration ran.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field

MAIN = "main"
BUDGET_SCRIPT = "jarvis-personal/backend/scripts/check_file_size_budget.py"
MIGRATIONS_DIR = "jarvis-personal/database/migrations/"
LABEL_STACKED = "stacked-approved"
LABEL_BUDGET = "budget-increase-approved"
LABEL_MIGRATION = "migration-gate-acknowledged"


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def check_base(base_ref: str, labels: set[str], result: Result) -> None:
    if base_ref == MAIN:
        return
    message = (
        f"PR base is '{base_ref}', not '{MAIN}'. A PR merged into another branch only reaches "
        f"'{MAIN}' if that branch is merged afterwards; if it was already merged, these commits are lost."
    )
    (result.warnings if LABEL_STACKED in labels else result.errors).append(
        message + ("" if LABEL_STACKED not in labels else f" (allowed by '{LABEL_STACKED}')")
    )


def check_hidden_stacking(pr_commits: set[str], open_prs: list[dict], own_number: int,
                          labels: set[str], result: Result) -> None:
    stacked = sorted(
        pr["number"] for pr in open_prs
        if pr.get("number") != own_number and pr.get("headRefOid") in pr_commits
    )
    if not stacked:
        return
    message = (
        "This PR contains the head commit of open PR(s) "
        + ", ".join(f"#{number}" for number in stacked)
        + ": it was built on top of unmerged work. Branch from the current origin/main instead."
    )
    (result.warnings if LABEL_STACKED in labels else result.errors).append(message)


def check_merged_target(action: str, merged: bool, base_ref: str, result: Result) -> None:
    if action == "closed" and merged and base_ref != MAIN:
        result.errors.append(
            f"This PR was merged into '{base_ref}', not '{MAIN}'. Its commits are NOT in '{MAIN}' "
            "unless that branch is merged later. Verify with: git merge-base --is-ancestor <sha> origin/main"
        )


def parse_budgets(source: str) -> dict[str, int]:
    """Map 'relative/path' -> limit from the BUDGETS literal of check_file_size_budget.py."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "BUDGETS" for t in node.targets):
            budgets = {}
            for key, value in zip(node.value.keys, node.value.values):
                parts = [n.value for n in ast.walk(key) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                budgets["/".join(parts)] = int(ast.literal_eval(value))
            return budgets
    return {}


def check_budgets(base_source: str | None, head_source: str | None, labels: set[str], result: Result) -> None:
    if not base_source or not head_source:
        return
    base, head = parse_budgets(base_source), parse_budgets(head_source)
    problems = [
        f"'{path}' budget raised {limit} -> {head[path]}"
        for path, limit in base.items() if path in head and head[path] > limit
    ] + [f"'{path}' budget removed" for path in base if path not in head]
    if not problems:
        return
    message = ("File-size budgets are architectural limits: " + "; ".join(problems)
               + ". Extract a coherent module instead of raising the limit.")
    (result.warnings if LABEL_BUDGET in labels else result.errors).append(message)


def check_migrations(added_files: list[str], labels: set[str], result: Result) -> None:
    migrations = sorted(path for path in added_files if path.startswith(MIGRATIONS_DIR))
    if not migrations:
        return
    message = (
        "PRE-MERGE GATE: this PR adds database migration(s): " + ", ".join(migrations)
        + ". Merging to main can deploy the backend immediately. A human must confirm the migration was "
        "applied in production first (or document why it is safe afterwards), then add the label "
        f"'{LABEL_MIGRATION}'. CI cannot see production."
    )
    (result.notes if LABEL_MIGRATION in labels else result.errors).append(message)


# --- CI entry point -----------------------------------------------------------

def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def _git_optional(*args: str) -> str | None:
    try:
        return _git(*args)
    except subprocess.CalledProcessError:
        return None


def _open_prs() -> list[dict]:
    output = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--limit", "200", "--json", "number,headRefOid"],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(output or "[]")


def run(event: dict) -> Result:
    result = Result()
    pr = event.get("pull_request") or {}
    action = event.get("action", "")
    base_ref = pr.get("base", {}).get("ref", "")
    labels = {label.get("name", "") for label in pr.get("labels", [])}

    check_merged_target(action, bool(pr.get("merged")), base_ref, result)
    if action == "closed":
        return result

    check_base(base_ref, labels, result)
    head_sha = pr.get("head", {}).get("sha", "")
    base = f"origin/{base_ref}"
    pr_commits = set(_git("rev-list", f"{base}..{head_sha}").split())
    check_hidden_stacking(pr_commits, _open_prs(), int(pr.get("number") or 0), labels, result)
    check_budgets(_git_optional("show", f"{base}:{BUDGET_SCRIPT}"),
                  _git_optional("show", f"{head_sha}:{BUDGET_SCRIPT}"), labels, result)
    added = _git("diff", "--name-only", "--diff-filter=A", f"{base}...{head_sha}").split()
    check_migrations(added, labels, result)
    return result


def main() -> int:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as handle:
        event = json.load(handle)
    result = run(event)
    lines = []
    for kind, messages in (("error", result.errors), ("warning", result.warnings), ("notice", result.notes)):
        for message in messages:
            print(f"::{kind}::{message}")
            lines.append(f"- **{kind.upper()}**: {message}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## PR guards\n\n" + ("\n".join(lines) if lines else "All PR guards passed.") + "\n")
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
