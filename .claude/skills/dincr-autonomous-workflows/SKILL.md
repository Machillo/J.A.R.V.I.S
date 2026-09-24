---
name: dincr-autonomous-workflows
description: Run delegated or unattended DINCR engineering work across one or more tasks — investigation, implementation, tests, review, commit, push and PR — with one fresh branch per task from current main, no stacking, checkpoints and strict production gates. Use when the user delegates several tasks or authorizes unattended work.
---

# DINCR Autonomous Workflows

The goal is as much safely completed, independently reviewable work as possible, with `main` and production untouched.

## Per-task loop

For each task, in dependency order:

1. **Preflight:** `git fetch origin`, then `git checkout -b <new-task-branch> origin/main`. Always a **new** branch from the **current** `origin/main`, never a previous task's branch.
2. **Investigate:** targeted search. Understand the execution path before editing.
3. **Implement:** the smallest correct change, following existing patterns. No unrelated refactors.
4. **Validate:** focused tests first. For bugs, a regression test that fails without the fix.
5. **Review:** apply `dincr-release-review`, plus `dincr-data-integrity`, `dincr-mobile-security-qa` or `dincr-finance` when the risk warrants. Use a reviewer role (`.claude/agents/`) for non-trivial or sensitive changes; if the host can't load it, do the review in the main session with the same checklist and say so.
6. **Correct:** in-scope findings only.
7. **Final validation:** the task's full required checks.
8. **Commit:** focused commits; never mix tasks.
9. **Push and PR:** open a PR with `base=main`. Run the PR preflight.
10. **Checkpoint:** task, branch, PR, commits, tests, gates, findings, remaining validation. Then continue.

## Dependencies: no silent stacking

- **Independent tasks:** each gets its own branch from `origin/main`.
- **A task that needs another task's unmerged changes:** **do not stack.**
  - Record the dependency.
  - Mark the task BLOCKED (waiting for the other PR to reach `main`).
  - Continue with independent tasks.
- **Stacking** (a branch or PR based on another unmerged branch) is allowed only when Kenneth explicitly authorizes it for that case. Even then, record it in both PRs and verify, after merge, that the commits actually reached `main`: GitHub can show MERGED for a PR merged into a base branch that was already merged.

## Escalate only for real blockers

Stop and escalate when progress needs:
- credentials or access;
- a high-impact product decision;
- a destructive operation;
- a production change;
- an unresolved security or data-integrity risk;
- blocking physical validation;
- a decision between contradictory requirements.

Routine test failures are debugged, not escalated. One blocked task does not stop independent ones.

## Human gates (never, even when working unattended)

- Merging to `main`.
- Deploying.
- Production migrations.
- Changing production secrets or config.
- Deleting production data.
- Store publishing.
- Other destructive or irreversible external actions.

"Work while I sleep" is not permission for any of these. Merge = possible deploy: list PRE-MERGE GATES in each PR.

## Context

- **Durable state:** Git, PRs and checkpoints are the durable state. Before compaction, preserve the checkpoint; after resuming, read it and `gh pr list` / `git log` before rediscovering anything.
- **Efficiency:** apply `dincr-efficient-coding`. Token savings never override correctness, security, privacy or financial integrity.

## Physical testing

If a task needs a device test you can't perform:
- finish the code and the automated validation;
- document the exact physical test;
- open the PR;
- continue with other tasks.

Never mark physical validation as done.

## Final handoff

- **COMPLETED:** task → PR (base=main).
- **BLOCKED:** task → exact blocker (including "waiting for PR X to reach main").
- **PRE-MERGE GATES.**
- **VALIDATION STILL REQUIRED.**
- **IMPORTANT FINDINGS.**
- **NEXT HUMAN ACTION.**

No diaries.
